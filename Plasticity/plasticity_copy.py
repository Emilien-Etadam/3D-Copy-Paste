#!/usr/bin/env python3
# OD_CopyPasteExternal — Copy From Plasticity (Python 3, stdlib only)
#
# Connects to Plasticity's bridge server (the same WebSocket protocol used
# by Nick Kallen's official Blender addon, MIT-licensed:
# https://github.com/nkallen/plasticity-blender-addon) and writes the
# visible solids/sheets to the ODVertexData exchange file, ready to paste
# in any supported application.
#
# Plasticity facets are triangles in right-handed Y-up space — the exchange
# file's native conventions — so geometry passes through unchanged.
#
# Usage:
#   plasticity_copy.py                 one-shot copy of the visible objects
#   plasticity_copy.py --all           include hidden objects
#   plasticity_copy.py --watch        keep running; re-copy on every change
#   plasticity_copy.py --server host:port   (default localhost:8980)
#
# In Plasticity, enable the bridge first (File > Settings > General >
# "Run in server mode" / the plug icon), then run this script.
#
# Paste INTO Plasticity: use tools/od_obj.py --to-obj and File > Import.

import argparse
import base64
import importlib.util
import os
import socket
import struct
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ODFORMAT_PATH = os.path.join(_REPO, "Blender", "od_copy_paste_external", "odformat.py")


def load_odformat():
    if not os.path.exists(_ODFORMAT_PATH):
        sys.exit("error: cannot find odformat.py at %s (run from a full checkout)" % _ODFORMAT_PATH)
    spec = importlib.util.spec_from_file_location("odformat", _ODFORMAT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["odformat"] = module
    spec.loader.exec_module(module)
    return module


odformat = load_odformat()

# ---- Plasticity bridge protocol constants -----------------------------------

TRANSACTION = 0
ADD = 1
UPDATE = 2
DELETE = 3
LIST_ALL = 20
LIST_VISIBLE = 22
SUBSCRIBE_ALL = 23
HANDSHAKE = 100

TYPE_SOLID = 0
TYPE_SHEET = 1


# ---- minimal RFC 6455 WebSocket client (client-side, no TLS) ----------------

class WebSocketError(ConnectionError):
    pass


class MiniWebSocket:
    """Just enough of RFC 6455 to talk to Plasticity on localhost."""

    def __init__(self, host, port, timeout=10.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            "GET / HTTP/1.1\r\n"
            "Host: %s:%d\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (host, port, key)
        )
        self.sock.sendall(request.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WebSocketError("connection closed during handshake")
            response += chunk
        header, _, leftover = response.partition(b"\r\n\r\n")
        self._buffer = bytearray(leftover)  # frames may ride the same packet
        status = header.split(b"\r\n", 1)[0]
        if b"101" not in status:
            raise WebSocketError("server refused the WebSocket upgrade: %r" % status)

    def _recv_exact(self, n):
        data = bytearray()
        if self._buffer:
            take = self._buffer[:n]
            del self._buffer[: len(take)]
            data.extend(take)
        while len(data) < n:
            chunk = self.sock.recv(min(65536, n - len(data)))
            if not chunk:
                raise WebSocketError("connection closed mid-frame")
            data.extend(chunk)
        return bytes(data)

    def send_binary(self, payload):
        header = bytearray([0x82])  # FIN + binary opcode
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 1 << 16:
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _send_control(self, opcode, payload=b""):
        mask = os.urandom(4)
        frame = bytearray([0x80 | opcode, 0x80 | len(payload)]) + mask
        frame += bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(frame))

    def recv_message(self, timeout=None):
        """Return the next complete binary/text message payload."""
        self.sock.settimeout(timeout)
        message = bytearray()
        while True:
            b1, b2 = self._recv_exact(2)
            fin, opcode = b1 & 0x80, b1 & 0x0F
            masked, length = b2 & 0x80, b2 & 0x7F
            if length == 126:
                (length,) = struct.unpack(">H", self._recv_exact(2))
            elif length == 127:
                (length,) = struct.unpack(">Q", self._recv_exact(8))
            mask = self._recv_exact(4) if masked else None
            payload = self._recv_exact(length) if length else b""
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x9:  # ping -> pong
                self._send_control(0xA, payload)
                continue
            if opcode == 0xA:  # pong
                continue
            if opcode == 0x8:  # close
                raise WebSocketError("server closed the connection")
            message.extend(payload)
            if fin:
                return bytes(message)

    def close(self):
        try:
            self._send_control(0x8)
        except OSError:
            pass
        self.sock.close()


# ---- protocol encoding/decoding (pure functions) -----------------------------

def build_simple(message_type, message_id):
    return struct.pack("<II", message_type, message_id)


def _u32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def _pad4(n):
    return (4 - (n % 4)) % 4


def decode_object(view, offset):
    """Decode one object record; return (object dict or None, new offset)."""
    object_type = _u32(view, offset)
    object_id = _u32(view, offset + 4)
    # version_id, parent_id, material_id, flags occupy offset+8 .. offset+24
    name_length = _u32(view, offset + 24)
    name = view[offset + 28 : offset + 28 + name_length].decode("utf-8", "replace")
    offset += 28 + name_length + _pad4(name_length)

    obj = None
    if object_type in (TYPE_SOLID, TYPE_SHEET):
        num_vertices = _u32(view, offset)
        offset += 4
        vertices = struct.unpack_from("<%df" % (num_vertices * 3), view, offset)
        offset += num_vertices * 12
        num_faces = _u32(view, offset)
        offset += 4
        faces = struct.unpack_from("<%di" % (num_faces * 3), view, offset)
        offset += num_faces * 12
        num_normals = _u32(view, offset)
        offset += 4 + num_normals * 12  # normals: skipped (deprecated in format)
        num_groups = _u32(view, offset)
        offset += 4 + num_groups * 4
        num_face_ids = _u32(view, offset)
        offset += 4 + num_face_ids * 4
        obj = {
            "id": object_id,
            "name": name or ("Solid" if object_type == TYPE_SOLID else "Sheet"),
            "vertices": vertices,
            "faces": faces,
        }
    return obj, offset


def decode_transaction(view, offset):
    """Decode a transaction; return {'add': [...], 'update': [...], 'delete': [ids]}."""
    result = {"add": [], "update": [], "delete": []}
    filename_length = _u32(view, offset)
    offset += 4 + filename_length + _pad4(filename_length)
    offset += 4  # version
    num_messages = _u32(view, offset)
    offset += 4
    for _ in range(num_messages):
        item_length = _u32(view, offset)
        offset += 4
        item = view[offset : offset + item_length]
        offset += item_length
        message_type = _u32(item, 0)
        if message_type in (ADD, UPDATE):
            num_objects = _u32(item, 4)
            item_offset = 8
            bucket = result["add"] if message_type == ADD else result["update"]
            for _ in range(num_objects):
                obj, item_offset = decode_object(item, item_offset)
                if obj is not None:
                    bucket.append(obj)
        elif message_type == DELETE:
            num_objects = _u32(item, 4)
            for k in range(num_objects):
                result["delete"].append(_u32(item, 8 + k * 4))
    return result


def objects_to_odmesh(objects, scale=1.0):
    """Merge Plasticity objects into one ODMesh (triangles, Y-up identity)."""
    mesh = odformat.ODMesh()
    for obj in objects:
        offset = len(mesh.vertices)
        verts = obj["vertices"]
        for i in range(0, len(verts), 3):
            mesh.vertices.append((verts[i] * scale, verts[i + 1] * scale, verts[i + 2] * scale))
        surface = obj["name"].replace(";;", "__") or "Default"
        faces = obj["faces"]
        for i in range(0, len(faces), 3):
            mesh.polygons.append(
                odformat.ODPolygon(
                    [offset + faces[i], offset + faces[i + 1], offset + faces[i + 2]],
                    surface,
                    "FACE",
                )
            )
    return mesh


# ---- client flow --------------------------------------------------------------

def write_exchange_file(objects, out, scale):
    mesh = objects_to_odmesh(objects, scale)
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write(odformat.serialize(mesh))
    print(
        "copied %d object(s): %d vertices / %d triangles -> %s"
        % (len(objects), len(mesh.vertices), len(mesh.polygons), out)
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Copy visible Plasticity objects to the ODVertexData exchange file.")
    parser.add_argument("--server", default="localhost:8980", help="Plasticity bridge address (default localhost:8980)")
    parser.add_argument("--all", action="store_true", help="include hidden objects (LIST_ALL instead of LIST_VISIBLE)")
    parser.add_argument("--watch", action="store_true", help="stay connected and re-copy on every Plasticity change")
    parser.add_argument("--scale", type=float, default=1.0, help="unit scale applied to coordinates (default 1.0)")
    parser.add_argument("--out", help="output file (default: shared exchange location)")
    args = parser.parse_args(argv)

    host, _, port = args.server.partition(":")
    out = args.out or odformat.data_file_path()

    try:
        ws = MiniWebSocket(host, int(port or 8980))
    except OSError as exc:
        sys.exit(
            "cannot connect to Plasticity at %s (%s).\n"
            "Is Plasticity running with the bridge server enabled?" % (args.server, exc)
        )

    try:
        message_id = 1
        ws.send_binary(build_simple(HANDSHAKE, message_id))
        reply = ws.recv_message(timeout=10)
        if _u32(reply, 0) != HANDSHAKE:
            sys.exit("unexpected handshake reply (message type %d)" % _u32(reply, 0))

        message_id += 1
        list_type = LIST_ALL if args.all else LIST_VISIBLE
        ws.send_binary(build_simple(list_type, message_id))
        reply = ws.recv_message(timeout=30)
        while _u32(reply, 0) not in (LIST_ALL, LIST_VISIBLE):
            reply = ws.recv_message(timeout=30)  # skip unsolicited broadcasts
        code = _u32(reply, 8)
        if code != 200:
            sys.exit("Plasticity returned error code %d for the list request" % code)
        transaction = decode_transaction(reply, 12)
        cache = {obj["id"]: obj for obj in transaction["add"] + transaction["update"]}
        if not cache:
            sys.exit("no visible solids/sheets in Plasticity (try --all, or unhide objects).")
        write_exchange_file(list(cache.values()), out, args.scale)

        if args.watch:
            message_id += 1
            ws.send_binary(build_simple(SUBSCRIBE_ALL, message_id))
            print("watching Plasticity for changes (Ctrl-C to stop)...")
            while True:
                try:
                    message = ws.recv_message(timeout=None)
                except KeyboardInterrupt:
                    print("stopped.")
                    break
                if _u32(message, 0) != TRANSACTION:
                    continue
                transaction = decode_transaction(message, 4)
                for obj in transaction["add"] + transaction["update"]:
                    cache[obj["id"]] = obj
                for deleted in transaction["delete"]:
                    cache.pop(deleted, None)
                if cache:
                    write_exchange_file(list(cache.values()), out, args.scale)
    finally:
        ws.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
