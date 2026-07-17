# Unit tests for the ODVertexData parser/writer (no Blender required).
#
# Run: python3 tests/test_odformat.py
# Exit code 0 = pass. Covers the reader-conformance checklist of
# docs/FORMAT.md section 8 against the pure-Python odformat module shared with
# the Blender extension.

import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_odformat():
    path = os.path.join(REPO, "Blender", "od_copy_paste_external", "odformat.py")
    spec = importlib.util.spec_from_file_location("odformat", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["odformat"] = module  # dataclasses needs the module registered
    spec.loader.exec_module(module)
    return module


def main():
    odformat = load_odformat()

    # Upstream reference file: mixed UV forms, None weights/morphs.
    with open(os.path.join(REPO, "docs", "datafile_example.txt"), encoding="utf-8") as f:
        text = f.read()
    mesh = odformat.parse(text)
    assert len(mesh.vertices) == 8 and len(mesh.polygons) == 6
    assert list(mesh.weight_maps) == ["simpleweights"]
    assert all(w == 1.0 for w in mesh.weight_maps["simpleweights"])
    morph = mesh.morph_maps["simplemorph"]
    assert morph[0] is None and morph[2] == (0.0, 0.290000021458, 0.0)
    uv = mesh.uv_maps["txuvmap"]
    discontinuous = [s for s in uv if s.polygon is not None]
    continuous = [s for s in uv if s.polygon is None]
    assert len(discontinuous) == 16 and len(continuous) == 8

    # Serialization round-trip is loss-free.
    again = odformat.parse(odformat.serialize(mesh))
    assert again.vertices == mesh.vertices
    assert [(p.indices, p.surface, p.ptype) for p in again.polygons] == [
        (p.indices, p.surface, p.ptype) for p in mesh.polygons
    ]
    assert again.weight_maps == mesh.weight_maps
    assert again.morph_maps == mesh.morph_maps
    assert [(s.u, s.v, s.polygon, s.vertex) for s in again.uv_maps["txuvmap"]] == [
        (s.u, s.v, s.polygon, s.vertex) for s in mesh.uv_maps["txuvmap"]
    ]

    # Golden files parse.
    for name in ("cube_uv.txt", "weighted_plane.txt"):
        with open(os.path.join(REPO, "tests", "golden", name), encoding="utf-8") as f:
            golden = odformat.parse(f.read())
        assert golden.vertices and golden.polygons and golden.uv_maps

    # CRLF endings, SUBD polytype, weight None and scientific notation,
    # Lightwave VERTEXNORMALS dialect skipped.
    lw = (
        "VERTICES:3\r\n0 0 0\r\n1 0 0\r\n0 1 0\r\n"
        "POLYGONS:1\r\n0,1,2;;Mat A;;SUBD\r\n"
        "VERTEXNORMALS:3\r\n0 0 1\r\n0 0 1\r\n0 0 1\r\n"
        "WEIGHT:w\r\n0.5\r\nNone\r\n1e-05\r\n"
    )
    mesh = odformat.parse(lw)
    assert mesh.polygons[0].ptype == "SUBD" and mesh.polygons[0].surface == "Mat A"
    assert mesh.weight_maps["w"] == [0.5, None, 1e-05]

    # Modo VERTEXNORMALS dialect skipped too.
    modo = (
        "VERTICES:3\n0 0 0\n1 0 0\n0 1 0\nPOLYGONS:1\n0,1,2;;Default;;FACE\n"
        "VERTEXNORMALS:VertexNormals:3\n0 0 1:PLY:0:PNT:0\n0 0 1:PLY:0:PNT:1\n0 0 1:PLY:0:PNT:2\n"
    )
    assert len(odformat.parse(modo).polygons) == 1

    # Error paths: missing VERTICES, truncated section, out-of-range index,
    # invalid map name on write.
    for bad in (
        "POLYGONS:1\n0,1,2;;a;;FACE\n",
        "VERTICES:2\n0 0 0\n",
        "VERTICES:3\n0 0 0\n1 0 0\n0 1 0\nPOLYGONS:1\n0,1,9;;a;;FACE\n",
    ):
        try:
            odformat.parse(bad)
            raise AssertionError("should have raised: %r" % bad)
        except odformat.ODFormatError:
            pass
    try:
        odformat.serialize(
            odformat.ODMesh(vertices=[(0, 0, 0)], weight_maps={"a:b": [1.0]})
        )
        raise AssertionError("invalid map name accepted")
    except odformat.ODFormatError:
        pass

    # OD_CPE_PATH override.
    os.environ["OD_CPE_PATH"] = os.path.join("some", "share")
    try:
        assert odformat.data_file_path() == os.path.join("some", "share", "ODVertexData.txt")
    finally:
        del os.environ["OD_CPE_PATH"]

    print("PASS test_odformat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
