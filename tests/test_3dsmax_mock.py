# Unit tests for the 3ds Max scripts' pure logic, runnable without Max.
#
# The pymxs module is replaced by a stub at import time; only the format
# functions are exercised (serialize, parse, fan triangulation, UV
# resolution). Real Max behavior is covered by the manual checklist in
# docs/TESTING.md.
#
# Run: python3 tests/test_3dsmax_mock.py

import importlib.util
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(REPO, "tests", "golden")


def install_fake_pymxs():
    pymxs = types.ModuleType("pymxs")
    pymxs.runtime = types.SimpleNamespace(
        Name=lambda s: s,
        units=types.SimpleNamespace(SystemType="meters", SystemScale=1.0),
        messageBox=lambda s: None,
    )
    sys.modules["pymxs"] = pymxs


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    install_fake_pymxs()
    copy_mod = load(os.path.join(REPO, "3DSMax", "3DSMax_CopyToExternal.py"), "max_copy")
    paste_mod = load(os.path.join(REPO, "3DSMax", "3DSMax_PasteFromExternal.py"), "max_paste")

    # 1. serialize -> parse round-trip
    data = {
        "vertices": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0)],
        "polygons": [([0, 1, 2], "Steel")],
        "uv_samples": [(0.0, 0.0, 0, 0), (1.0, 0.0, 0, 1), (1.0, 1.0, 0, 2)],
    }
    parsed = paste_mod.parse(copy_mod.serialize(data))
    assert parsed["vertices"] == data["vertices"]
    assert parsed["polygons"] == [([0, 1, 2], "Steel")]
    assert parsed["uv_maps"]["UVMap"] == [(0.0, 0.0, 0, 0), (1.0, 0.0, 0, 1), (1.0, 1.0, 0, 2)]

    # 2. golden files parse; weight/morph names recorded for the skip notice
    golden = paste_mod.parse(open(os.path.join(GOLDEN_DIR, "cube_uv.txt"), encoding="utf-8").read())
    assert len(golden["vertices"]) == 8 and len(golden["polygons"]) == 6
    golden = paste_mod.parse(open(os.path.join(GOLDEN_DIR, "weighted_plane.txt"), encoding="utf-8").read())
    assert golden["weight_maps"] == ["edge_falloff", "left_side"]
    assert golden["morph_maps"] == ["bump"]

    # 3. triangulation: quad -> 2 tris, hexagon -> 4, degenerate handled,
    #    winding preserved (Max matches the format)
    polygons = [([0, 1, 2, 3], "a"), ([0, 1, 2, 3, 4, 5], "a"), ([0, 1, 1], "a")]
    triangles, kept = paste_mod.triangulate(polygons)
    assert triangles[:2] == [[0, 1, 2], [0, 2, 3]]
    assert len(triangles) == 6 and kept == [0, 0, 1, 1, 1, 1]

    # 4. UV resolution per triangle with discontinuous override
    samples = [(0.5, 0.5, None, 0), (0.1, 0.1, None, 1), (0.2, 0.2, None, 2),
               (0.3, 0.3, None, 3), (0.9, 0.9, 0, 0)]
    corner_uvs = paste_mod.resolve_corner_uvs(polygons[:1], triangles[:2], kept[:2], samples)
    assert corner_uvs[0][0] == (0.9, 0.9) and corner_uvs[1][0] == (0.9, 0.9)
    sparse = paste_mod.resolve_corner_uvs(polygons[:1], triangles[:2], kept[:2], samples[:2])
    assert sparse[0] is None

    # 5. unit mapping (fake runtime reports meters, scale 1.0)
    assert copy_mod.system_scale_to_meters() == 1.0

    # 6. malformed input raises
    for bad in ["POLYGONS:1\n0,1,2;;a;;FACE\n", "VERTICES:2\n0 0 0\n"]:
        try:
            paste_mod.parse(bad)
            raise AssertionError("should have raised: %r" % bad)
        except ValueError:
            pass

    print("all 3dsmax mock tests OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
