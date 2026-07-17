# Unit tests for the Cinema 4D scripts' pure logic, runnable without C4D.
#
# The c4d module is replaced by an empty stub at import time; only the
# format functions are exercised (serialize, parse, face building with
# winding reversal and n-gon fans, UV resolution, corner extraction).
# Real C4D behavior is covered by the manual checklist in docs/TESTING.md.
#
# Run: python3 tests/test_c4d_mock.py

import importlib.util
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(REPO, "tests", "golden")


def install_fake_c4d():
    c4d = types.ModuleType("c4d")
    c4d.documents = types.SimpleNamespace()
    c4d.gui = types.SimpleNamespace(MessageDialog=lambda s: None)
    sys.modules["c4d"] = c4d


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    install_fake_c4d()
    copy_mod = load(os.path.join(REPO, "C4D", "C4D_CopyToExternal.py"), "c4d_copy")
    paste_mod = load(os.path.join(REPO, "C4D", "C4D_PasteFromExternal.py"), "c4d_paste")

    # 1. serialize -> parse round-trip
    data = {
        "vertices": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
        "polygons": [([0, 1, 2, 3], "Steel")],
        "weight_maps": {"softness": [1.0, None, 0.25, 0.0]},
        "uv_samples": [(0.0, 0.0, 0, 0), (1.0, 0.0, 0, 1), (1.0, 1.0, 0, 2), (0.0, 1.0, 0, 3)],
    }
    parsed = paste_mod.parse(copy_mod.serialize(data))
    assert parsed["vertices"] == data["vertices"]
    assert parsed["polygons"] == [([0, 1, 2, 3], "Steel")]
    assert parsed["weight_maps"]["softness"] == [1.0, None, 0.25, 0.0]
    assert parsed["uv_maps"]["UVMap"] == [(0.0, 0.0, 0, 0), (1.0, 0.0, 0, 1), (1.0, 1.0, 0, 2), (0.0, 1.0, 0, 3)]

    # 2. golden files parse
    golden = paste_mod.parse(open(os.path.join(GOLDEN_DIR, "cube_uv.txt"), encoding="utf-8").read())
    assert len(golden["vertices"]) == 8 and len(golden["polygons"]) == 6
    assert len(golden["uv_maps"]["txuvmap"]) == 24
    golden = paste_mod.parse(open(os.path.join(GOLDEN_DIR, "weighted_plane.txt"), encoding="utf-8").read())
    assert golden["weight_maps"]["edge_falloff"][4] is None
    assert golden["morph_maps"] == {"bump": True}  # presence recorded, skipped on paste

    # 3. face building: winding reversed; quad kept; hexagon fan of 4 tris;
    #    degenerate quad collapsed to a triangle; 2-index polygon dropped
    polygons = [
        ([0, 1, 2, 3], "a"),
        ([0, 1, 2, 3, 4, 5], "a"),
        ([0, 1, 2, 2], "a"),
        ([0, 1, 1], "a"),
    ]
    faces, kept = paste_mod.build_faces(polygons)
    assert faces[0] == [3, 2, 1, 0]                      # quad reversed
    assert kept == [0, 1, 1, 1, 1, 2]
    assert faces[1:5] == [[2, 1, 0], [3, 2, 0], [4, 3, 0], [5, 4, 0]]  # reversed fan
    assert faces[5] == [2, 1, 0]                          # degenerate quad -> tri

    # 4. UV resolution follows kept mapping; discontinuous wins; incomplete -> None
    samples = [
        (0.5, 0.5, None, 0), (0.1, 0.1, None, 1), (0.2, 0.2, None, 2), (0.3, 0.3, None, 3),
        (0.9, 0.9, 0, 3),  # discontinuous override on quad corner
    ]
    corner_uvs = paste_mod.resolve_corner_uvs(polygons[:1], faces[:1], kept[:1], samples)
    assert corner_uvs[0][0] == (0.9, 0.9)  # face corner order [3,2,1,0]
    assert corner_uvs[0][3] == (0.5, 0.5)
    sparse = paste_mod.resolve_corner_uvs(polygons[:1], faces[:1], kept[:1], samples[:2])
    assert sparse[0] is None  # missing corners -> face unassigned

    # 5. copy-side helpers: CPolygon triangle convention (c == d)
    tri = types.SimpleNamespace(a=0, b=1, c=2, d=2)
    quad = types.SimpleNamespace(a=0, b=1, c=2, d=3)
    assert copy_mod.polygon_corners(tri) == [0, 1, 2]
    assert copy_mod.polygon_corners(quad) == [0, 1, 2, 3]

    # 6. malformed input raises
    for bad in ["POLYGONS:1\n0,1,2;;a;;FACE\n", "VERTICES:2\n0 0 0\n"]:
        try:
            paste_mod.parse(bad)
            raise AssertionError("should have raised: %r" % bad)
        except ValueError:
            pass

    print("all c4d mock tests OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
