# Unit tests for the Maya scripts' pure logic, runnable without Maya.
#
# The maya.api.OpenMaya / maya.cmds modules are replaced by empty stubs at
# import time; only the format functions are exercised (parse, serialize,
# face-array building, UV assignment resolution, component expansion).
# Real Maya behavior (MFnMesh.create, blendShape, shading) is covered by
# the manual checklist in docs/TESTING.md.
#
# Run: python3 tests/test_maya_mock.py

import importlib.util
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(REPO, "tests", "golden")


def install_fakes():
    maya = types.ModuleType("maya")
    maya_api = types.ModuleType("maya.api")
    om = types.ModuleType("maya.api.OpenMaya")
    om.MGlobal = types.SimpleNamespace(
        displayInfo=lambda s: None, displayWarning=lambda s: None
    )
    oma = types.ModuleType("maya.api.OpenMayaAnim")
    cmds = types.ModuleType("maya.cmds")
    maya.api = maya_api
    maya.cmds = cmds
    maya_api.OpenMaya = om
    maya_api.OpenMayaAnim = oma
    sys.modules.update(
        {
            "maya": maya,
            "maya.api": maya_api,
            "maya.api.OpenMaya": om,
            "maya.api.OpenMayaAnim": oma,
            "maya.cmds": cmds,
        }
    )


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    install_fakes()
    export_mod = load(os.path.join(REPO, "Maya", "maya_ExportToExternal.py"), "maya_export")
    paste_mod = load(os.path.join(REPO, "Maya", "maya_PasteFromExternal.py"), "maya_paste")

    # 1. serialize -> parse round-trip of a synthetic collect() result
    data = {
        "vertices": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
        "polygons": [([0, 1, 2, 3], "Steel")],
        "weight_maps": {"joint1": [1.0, 0.5, None, 0.0]},
        "morph_maps": {"smile": [None, (0.0, 0.1, 0.0), None, None]},
        "uv_maps": {"map1": [(0.0, 0.0, 0, 0), (1.0, 0.0, 0, 1), (1.0, 1.0, 0, 2), (0.0, 1.0, 0, 3)]},
    }
    text = export_mod.serialize(data)
    assert text.startswith("VERTICES:4\n")
    parsed = paste_mod.parse(text)
    assert parsed["vertices"] == data["vertices"]
    assert parsed["polygons"] == [([0, 1, 2, 3], "Steel", "FACE")]
    assert parsed["weight_maps"]["joint1"] == [1.0, 0.5, None, 0.0]
    assert parsed["morph_maps"]["smile"][1] == (0.0, 0.1, 0.0)
    assert parsed["uv_maps"]["map1"] == [(0.0, 0.0, 0, 0), (1.0, 0.0, 0, 1), (1.0, 1.0, 0, 2), (0.0, 1.0, 0, 3)]

    # 2. golden files parse (mixed UV forms, weights and morphs with None)
    golden = open(os.path.join(GOLDEN_DIR, "cube_uv.txt"), encoding="utf-8").read()
    parsed = paste_mod.parse(golden)
    assert len(parsed["vertices"]) == 8 and len(parsed["polygons"]) == 6
    assert len(parsed["uv_maps"]["txuvmap"]) == 24

    golden = open(os.path.join(GOLDEN_DIR, "weighted_plane.txt"), encoding="utf-8").read()
    parsed = paste_mod.parse(golden)
    assert parsed["weight_maps"]["edge_falloff"][4] is None
    assert parsed["morph_maps"]["bump"][4] == (0.0, 0.5, 0.0)

    # 3. face arrays: n-gon kept natively, degenerate quad collapsed, 2-pt dropped
    polygons = [
        ([0, 1, 2, 3, 4, 5], "Default", "FACE"),
        ([0, 1, 2, 2], "Default", "FACE"),
        ([0, 1, 1], "Default", "FACE"),
    ]
    counts, connects, kept = paste_mod.build_face_arrays(polygons)
    assert counts == [6, 3] and kept == [0, 1]
    assert connects == [0, 1, 2, 3, 4, 5, 0, 1, 2]

    # 4. UV assignment: discontinuous beats continuous; face with a hole -> count 0
    polygons = [([0, 1, 2], "a", "FACE"), ([2, 3, 0], "a", "FACE")]
    counts, connects, kept = paste_mod.build_face_arrays(polygons)
    samples = [
        (0.5, 0.5, None, 0), (0.1, 0.1, None, 1), (0.2, 0.2, None, 2),
        (0.9, 0.9, 0, 0),  # discontinuous override for corner (0, 0)
        # vertex 3 has no UV at all -> face 1 unassigned
    ]
    uv_values, uv_counts, uv_ids = paste_mod.resolve_uv_assignment(polygons, kept, samples)
    assert uv_counts == [3, 0]
    assert uv_values[uv_ids[0]] == (0.9, 0.9)  # override applied
    assert uv_values[uv_ids[1]] == (0.1, 0.1)
    assert len(uv_ids) == 3

    # 5. component-string expansion (blend-shape sparse targets)
    assert export_mod.expand_components(["vtx[3]", "vtx[5:8]"]) == [3, 5, 6, 7, 8]
    assert export_mod.expand_components(None) == []

    # 6. node-name sanitizing
    assert paste_mod.sanitize("my map:2") == "my_map_2"
    assert paste_mod.sanitize("2sided") == "_2sided"

    # 7. malformed input raises
    for bad in ["POLYGONS:1\n0,1,2;;a;;FACE\n", "VERTICES:2\n0 0 0\n"]:
        try:
            paste_mod.parse(bad)
            raise AssertionError("should have raised: %r" % bad)
        except ValueError:
            pass

    print("all maya mock tests OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
