#!/usr/bin/env python3
# OD_CopyPasteExternal — OBJ <-> ODVertexData converter (Python 3, stdlib only)
#
# Cross-platform replacement for the historical compiled Windows converters
# (objToVertData.exe / vertDataToObj.exe) used by the ZBrush, Substance
# Painter, 3D-Coat, C4D and Moi3D integrations, and the entry point for any
# application that speaks OBJ but has no scripting API (Plasticity via
# File > Import/Export, Light Tracer Render, ...).
#
# The exchange format (docs/FORMAT.md) uses the OBJ coordinate conventions
# (right-handed, Y-up, CCW winding), so the conversion is purely structural:
# 1-based <-> 0-based indices, usemtl <-> surface names, vt <-> UV samples.
# Weight and morph maps have no OBJ equivalent and are dropped with a notice
# when converting to OBJ.
#
# Usage:
#   od_obj.py --from-obj model.obj [--out ODVertexData.txt]
#       Convert an OBJ file to the exchange file (defaults to the shared
#       location: $OD_CPE_PATH or the system temp directory).
#   od_obj.py --to-obj [model.obj] [--in ODVertexData.txt]
#       Convert the exchange file to OBJ (defaults: read the shared
#       location, write OD_CPE.obj next to it).

import argparse
import importlib.util
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ODFORMAT_PATH = os.path.join(_REPO, "Blender", "od_copy_paste_external", "odformat.py")


def load_odformat():
    if not os.path.exists(_ODFORMAT_PATH):
        sys.exit(
            "error: cannot find odformat.py (expected at %s). Run this tool "
            "from a full checkout of the repository." % _ODFORMAT_PATH
        )
    spec = importlib.util.spec_from_file_location("odformat", _ODFORMAT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["odformat"] = module
    spec.loader.exec_module(module)
    return module


odformat = load_odformat()


def obj_to_odmesh(text):
    """Parse Wavefront OBJ text into an odformat.ODMesh."""
    mesh = odformat.ODMesh()
    uvs = []  # (u, v) in vt order
    surface = "Default"
    samples = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        keyword = parts[0]
        if keyword == "v" and len(parts) >= 4:
            mesh.vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif keyword == "vt" and len(parts) >= 3:
            uvs.append((float(parts[1]), float(parts[2])))
        elif keyword == "usemtl" and len(parts) >= 2:
            surface = " ".join(parts[1:]).replace(";;", "__")
        elif keyword == "f" and len(parts) >= 4:
            indices = []
            face_index = len(mesh.polygons)
            for corner in parts[1:]:
                fields = corner.split("/")
                vi = int(fields[0])
                # OBJ indices are 1-based; negative indices count from the end
                vi = vi - 1 if vi > 0 else len(mesh.vertices) + vi
                if not 0 <= vi < len(mesh.vertices):
                    raise ValueError("face vertex index out of range: %r" % corner)
                indices.append(vi)
                if len(fields) > 1 and fields[1]:
                    ti = int(fields[1])
                    ti = ti - 1 if ti > 0 else len(uvs) + ti
                    if 0 <= ti < len(uvs):
                        samples.append(
                            odformat.UVSample(uvs[ti][0], uvs[ti][1], face_index, vi)
                        )
            mesh.polygons.append(odformat.ODPolygon(indices, surface, "FACE"))
    if samples:
        mesh.uv_maps["UVMap"] = samples
    return mesh


def odmesh_to_obj(mesh, name="ODVertexData"):
    """Serialize an odformat.ODMesh to Wavefront OBJ text.

    Returns (obj_text, dropped) where dropped lists the weight/morph map
    names that OBJ cannot carry.
    """
    lines = ["o " + name]
    for v in mesh.vertices:
        lines.append("v %r %r %r" % (float(v[0]), float(v[1]), float(v[2])))

    # Resolve UV samples (first map) to one vt per distinct (u, v) and a
    # per-polygon-corner index; discontinuous samples override continuous.
    corner_uv = {}
    if mesh.uv_maps:
        first = next(iter(mesh.uv_maps))
        continuous, discontinuous = {}, {}
        for s in mesh.uv_maps[first]:
            if s.polygon is None:
                continuous[s.vertex] = (s.u, s.v)
            else:
                discontinuous[(s.polygon, s.vertex)] = (s.u, s.v)
        vt_index = {}
        for p, poly in enumerate(mesh.polygons):
            for v in poly.indices:
                uv = discontinuous.get((p, v), continuous.get(v))
                if uv is None:
                    continue
                if uv not in vt_index:
                    vt_index[uv] = len(vt_index) + 1  # OBJ is 1-based
                    lines.append("vt %r %r" % (float(uv[0]), float(uv[1])))
                corner_uv[(p, v)] = vt_index[uv]

    current_surface = None
    for p, poly in enumerate(mesh.polygons):
        surface = poly.surface or "Default"
        if surface != current_surface:
            lines.append("usemtl " + surface)
            current_surface = surface
        corners = []
        for v in poly.indices:
            vt = corner_uv.get((p, v))
            corners.append("%d/%d" % (v + 1, vt) if vt else str(v + 1))
        lines.append("f " + " ".join(corners))

    dropped = sorted(mesh.weight_maps) + sorted(mesh.morph_maps)
    return "\n".join(lines) + "\n", dropped


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert between Wavefront OBJ and the ODVertexData exchange file."
    )
    direction = parser.add_mutually_exclusive_group(required=True)
    direction.add_argument("--from-obj", metavar="OBJ", help="OBJ file to convert to the exchange file")
    direction.add_argument(
        "--to-obj", metavar="OBJ", nargs="?", const="", help="convert the exchange file to OBJ"
    )
    parser.add_argument("--in", dest="input", metavar="FILE", help="exchange file to read (default: shared location)")
    parser.add_argument("--out", metavar="FILE", help="file to write (default: shared location / OD_CPE.obj)")
    args = parser.parse_args(argv)

    if args.from_obj is not None:
        with open(args.from_obj, "r", encoding="utf-8", errors="replace") as f:
            mesh = obj_to_odmesh(f.read())
        out = args.out or odformat.data_file_path()
        with open(out, "w", encoding="utf-8", newline="") as f:
            f.write(odformat.serialize(mesh))
        print(
            "wrote %s (%d vertices, %d polygons, %d UV samples)"
            % (out, len(mesh.vertices), len(mesh.polygons),
               sum(len(s) for s in mesh.uv_maps.values()))
        )
    else:
        src = args.input or odformat.data_file_path()
        with open(src, "r", encoding="utf-8", errors="replace") as f:
            mesh = odformat.parse(f.read())
        out = args.out or args.to_obj or os.path.join(
            os.path.dirname(src), "OD_CPE.obj"
        )
        text, dropped = odmesh_to_obj(mesh)
        with open(out, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print("wrote %s (%d vertices, %d polygons)" % (out, len(mesh.vertices), len(mesh.polygons)))
        if dropped:
            print("note: OBJ cannot carry weight/morph maps; dropped: " + ", ".join(dropped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
