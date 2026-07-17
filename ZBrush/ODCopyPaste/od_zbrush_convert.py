#!/usr/bin/env python3
# OD_CopyPasteExternal - ZBrush converter (Python 3, stdlib only)
#
# Cross-platform replacement for the compiled objToVertData.exe /
# vertDataToObj.exe (antivirus-flagged, unbuildable - upstream #34/#59).
# Launched by the ZScript through the od_export / od_import wrappers:
#
#   od_zbrush_convert.py export   1.OBJ (written by ZBrush) -> exchange file
#   od_zbrush_convert.py import   exchange file -> 1.OBJ (for ZBrush import)
#
# Self-contained on purpose: the ZBrush plugin folder is installed standalone
# in ZStartup/ZPlugs64, with no repository checkout around. The exchange
# format is docs/FORMAT.md in the repository; both ZBrush and OBJ share the
# format's conventions (right-handed Y-up, CCW winding, 0-based after the
# 1-based OBJ offset), so the conversion is purely structural.

import os
import sys
import tempfile

FILE_NAME = "ODVertexData.txt"
ENV_VAR = "OD_CPE_PATH"
OBJ_NAME = "1.OBJ"


def exchange_path():
    base = os.environ.get(ENV_VAR) or tempfile.gettempdir()
    return os.path.join(base, FILE_NAME)


def obj_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), OBJ_NAME)


def _num(value):
    return repr(float(value))


def obj_to_exchange(obj_text):
    """Wavefront OBJ text -> exchange-file text."""
    vertices, uvs, polygons, samples = [], [], [], []
    surface = "Default"
    for raw in obj_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0] == "v" and len(parts) >= 4:
            vertices.append((parts[1], parts[2], parts[3]))
        elif parts[0] == "vt" and len(parts) >= 3:
            uvs.append((parts[1], parts[2]))
        elif parts[0] == "usemtl" and len(parts) >= 2:
            surface = " ".join(parts[1:]).replace(";;", "__")
        elif parts[0] == "f" and len(parts) >= 4:
            indices = []
            face_index = len(polygons)
            for corner in parts[1:]:
                fields = corner.split("/")
                vi = int(fields[0])
                vi = vi - 1 if vi > 0 else len(vertices) + vi
                indices.append(vi)
                if len(fields) > 1 and fields[1]:
                    ti = int(fields[1])
                    ti = ti - 1 if ti > 0 else len(uvs) + ti
                    if 0 <= ti < len(uvs):
                        samples.append((uvs[ti][0], uvs[ti][1], face_index, vi))
            polygons.append((indices, surface))

    lines = ["VERTICES:%d" % len(vertices)]
    for v in vertices:
        lines.append("%s %s %s" % (_num(v[0]), _num(v[1]), _num(v[2])))
    lines.append("POLYGONS:%d" % len(polygons))
    for indices, poly_surface in polygons:
        lines.append(
            "%s;;%s;;FACE" % (",".join(str(i) for i in indices), poly_surface)
        )
    if samples:
        lines.append("UV:UVMap:%d" % len(samples))
        for u, v, face, vertex in samples:
            lines.append("%s %s:PLY:%d:PNT:%d" % (_num(u), _num(v), face, vertex))
    return "\n".join(lines) + "\n"


def exchange_to_obj(text):
    """Exchange-file text -> Wavefront OBJ text (verts, faces, UVs)."""
    lines = text.splitlines()
    vertices, polygons = [], []
    uv_samples = []

    vert_at = None
    for i, line in enumerate(lines):
        if line.startswith("VERTICES:"):
            vert_at = i
            break
    if vert_at is None:
        raise ValueError("no VERTICES section found")
    vcount = int(lines[vert_at].split(":")[1].strip())
    chunk = lines[vert_at + 1 : vert_at + 1 + vcount]
    if len(chunk) != vcount:
        raise ValueError("truncated VERTICES section")
    for vline in chunk:
        tokens = vline.split()
        if len(tokens) < 3:
            raise ValueError("bad vertex line: %r" % vline)
        vertices.append((float(tokens[0]), float(tokens[1]), float(tokens[2])))

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("VERTICES:"):
            i += 1 + vcount
        elif line.startswith("POLYGONS:"):
            count = int(line.split(":")[1].strip())
            for pline in lines[i + 1 : i + 1 + count]:
                parts = pline.split(";;")
                indices = [int(t.strip()) for t in parts[0].split(",")]
                surface = parts[1].strip() if len(parts) > 1 else "Default"
                polygons.append((indices, surface))
            i += 1 + count
        elif line.startswith("WEIGHT:") or line.startswith("MORPH:"):
            i += 1 + vcount  # no OBJ equivalent; dropped
        elif line.startswith("UV:"):
            head = line.split(":")
            count = int(head[2].strip())
            for uline in lines[i + 1 : i + 1 + count]:
                fields = uline.split(":")
                uv = fields[0].split()
                if len(fields) >= 5:
                    uv_samples.append((float(uv[0]), float(uv[1]), int(fields[2]), int(fields[4])))
                elif len(fields) == 3:
                    uv_samples.append((float(uv[0]), float(uv[1]), None, int(fields[2])))
            i += 1 + count
        elif line.startswith("VERTEXNORMALS"):
            try:
                count = int(line.split(":")[-1].strip())
            except ValueError:
                count = 0
            i += 1 + count
        else:
            i += 1

    continuous, discontinuous = {}, {}
    for u, v, poly, vertex in uv_samples:
        if poly is None:
            continuous[vertex] = (u, v)
        else:
            discontinuous[(poly, vertex)] = (u, v)

    out = ["o ODVertexData"]
    for x, y, z in vertices:
        out.append("v %s %s %s" % (_num(x), _num(y), _num(z)))
    vt_index = {}
    corner_vt = {}
    for p, (indices, _surface) in enumerate(polygons):
        for idx in indices:
            uv = discontinuous.get((p, idx), continuous.get(idx))
            if uv is None:
                continue
            if uv not in vt_index:
                vt_index[uv] = len(vt_index) + 1
                out.append("vt %s %s" % (_num(uv[0]), _num(uv[1])))
            corner_vt[(p, idx)] = vt_index[uv]
    current = None
    for p, (indices, surface) in enumerate(polygons):
        if surface != current:
            out.append("usemtl " + surface)
            current = surface
        corners = []
        for idx in indices:
            vt = corner_vt.get((p, idx))
            corners.append("%d/%d" % (idx + 1, vt) if vt else str(idx + 1))
        out.append("f " + " ".join(corners))
    return "\n".join(out) + "\n"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1 or argv[0] not in ("export", "import"):
        print("usage: od_zbrush_convert.py export|import")
        return 2
    if argv[0] == "export":
        with open(obj_path(), "r", encoding="utf-8", errors="replace") as f:
            text = obj_to_exchange(f.read())
        with open(exchange_path(), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print("wrote " + exchange_path())
    else:
        with open(exchange_path(), "r", encoding="utf-8", errors="replace") as f:
            text = exchange_to_obj(f.read())
        with open(obj_path(), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print("wrote " + obj_path())
    return 0


if __name__ == "__main__":
    sys.exit(main())
