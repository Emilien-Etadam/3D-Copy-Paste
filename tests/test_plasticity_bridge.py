# Unit tests for the Plasticity bridge client (Plasticity/plasticity_copy.py).
#
# The protocol decoding is exercised against hand-built binary buffers that
# follow the layout of Plasticity's bridge (as implemented by the official
# MIT-licensed Blender addon), and the embedded RFC 6455 client is tested
# over a real loopback socket against a minimal in-test server.
#
# Run: python3 tests/test_plasticity_bridge.py

import base64
import hashlib
import importlib.util
import os
import socket
import struct
import sys
import threading

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bridge = load(os.path.join(REPO, "Plasticity", "plasticity_copy.py"), "plasticity_copy")


def pad4(n):
    return (4 - (n % 4)) % 4


def encode_object(object_type, object_id, name, vertices=(), faces=()):
    name_b = name.encode()
    # field by field, matching the offsets the client expects
    buf = b"".join(
        [
            struct.pack("<I", object_type),
            struct.pack("<I", object_id),
            struct.pack("<I", 7),        # version_id
            struct.pack("<i", -1),       # parent_id
            struct.pack("<i", -1),       # material_id
            struct.pack("<I", 0),        # flags
            struct.pack("<I", len(name_b)),
            name_b,
            b"\x00" * pad4(len(name_b)),
        ]
    )
    if object_type in (bridge.TYPE_SOLID, bridge.TYPE_SHEET):
        buf += struct.pack("<I", len(vertices) // 3)
        buf += struct.pack("<%df" % len(vertices), *vertices)
        buf += struct.pack("<I", len(faces) // 3)
        buf += struct.pack("<%di" % len(faces), *faces)
        buf += struct.pack("<I", 0)  # normals
        buf += struct.pack("<I", 0)  # groups
        buf += struct.pack("<I", 0)  # face_ids
    return buf


def encode_transaction(filename, items):
    fn = filename.encode()
    buf = struct.pack("<I", len(fn)) + fn + b"\x00" * pad4(len(fn))
    buf += struct.pack("<I", 3)  # version
    buf += struct.pack("<I", len(items))
    for item in items:
        buf += struct.pack("<I", len(item)) + item
    return buf


def add_item(objects):
    return struct.pack("<II", bridge.ADD, len(objects)) + b"".join(objects)


def delete_item(ids):
    return struct.pack("<II", bridge.DELETE, len(ids)) + struct.pack("<%dI" % len(ids), *ids)


TRI = dict(
    vertices=(0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    faces=(0, 1, 2),
)


def test_decoding():
    # LIST_VISIBLE reply: type + message_id + code + transaction
    solid = encode_object(bridge.TYPE_SOLID, 11, "Body A", **TRI)
    group = encode_object(5, 12, "A Group")  # GROUP: no mesh payload
    sheet = encode_object(bridge.TYPE_SHEET, 13, "Panel", **TRI)
    reply = struct.pack("<III", bridge.LIST_VISIBLE, 2, 200) + encode_transaction(
        "part.plasticity", [add_item([solid, group, sheet]), delete_item([99])]
    )
    assert bridge._u32(reply, 8) == 200
    transaction = bridge.decode_transaction(reply, 12)
    assert [o["id"] for o in transaction["add"]] == [11, 13]  # GROUP skipped
    assert transaction["delete"] == [99]
    assert transaction["add"][0]["name"] == "Body A"

    mesh = bridge.objects_to_odmesh(transaction["add"], scale=2.0)
    assert len(mesh.vertices) == 6 and len(mesh.polygons) == 2
    assert mesh.vertices[1] == (2.0, 0.0, 0.0)  # scale applied
    assert mesh.polygons[1].indices == [3, 4, 5]  # offset applied
    assert mesh.polygons[0].surface == "Body A" and mesh.polygons[1].surface == "Panel"

    # serialized output must be valid exchange-file text
    reparsed = bridge.odformat.parse(bridge.odformat.serialize(mesh))
    assert len(reparsed.polygons) == 2


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def ws_server(server_sock, payloads):
    conn, _ = server_sock.accept()
    request = b""
    while b"\r\n\r\n" not in request:
        request += conn.recv(4096)
    key = [l.split(b": ", 1)[1] for l in request.split(b"\r\n") if l.lower().startswith(b"sec-websocket-key")][0]
    accept = base64.b64encode(hashlib.sha1(key + GUID.encode()).digest()).decode()
    conn.sendall(
        (
            "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n" % accept
        ).encode()
    )
    # send a ping, then each payload as (possibly fragmented) binary frames
    conn.sendall(bytes([0x89, 0x02]) + b"hi")
    for payload in payloads:
        half = len(payload) // 2
        conn.sendall(bytes([0x02]) + encode_len(half) + payload[:half])          # fragment 1
        conn.sendall(bytes([0x80]) + encode_len(len(payload) - half) + payload[half:])  # FIN cont.
    # read one client message (masked), echo nothing, close
    conn.recv(65536)
    conn.sendall(bytes([0x88, 0x00]))
    conn.close()


def encode_len(n):
    if n < 126:
        return bytes([n])
    if n < 1 << 16:
        return bytes([126]) + struct.pack(">H", n)
    return bytes([127]) + struct.pack(">Q", n)


def test_websocket_client():
    server_sock = socket.socket()
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]
    big = os.urandom(70000)  # forces the 16-bit and fragmented paths
    thread = threading.Thread(target=ws_server, args=(server_sock, [b"abc", big]), daemon=True)
    thread.start()

    ws = bridge.MiniWebSocket("127.0.0.1", port)
    assert ws.recv_message(timeout=5) == b"abc"       # ping was auto-answered
    assert ws.recv_message(timeout=5) == big          # fragmented + extended length
    ws.send_binary(bridge.build_simple(bridge.HANDSHAKE, 1))
    try:
        ws.recv_message(timeout=5)
        raise AssertionError("expected close")
    except bridge.WebSocketError:
        pass
    thread.join(timeout=5)


def main():
    test_decoding()
    test_websocket_client()
    print("all plasticity bridge tests OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
