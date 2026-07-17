# Unit tests for the ZBrush converter (ZBrush/ODCopyPaste/od_zbrush_convert.py).
#
# The converter is plain Python (no app module): both directions run
# directly, including a full OBJ -> exchange -> OBJ round-trip and the CLI
# through OD_CPE_PATH with a fake 1.OBJ.
#
# Run: python3 tests/test_zbrush_convert.py

import importlib.util
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(REPO, "tests", "golden")
CONVERTER = os.path.join(REPO, "ZBrush", "ODCopyPaste", "od_zbrush_convert.py")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    conv = load(CONVERTER, "od_zbrush_convert")

    # 1. golden cube: exchange -> OBJ -> exchange, geometry preserved
    golden_text = open(os.path.join(GOLDEN_DIR, "cube_uv.txt"), encoding="utf-8").read()
    obj_text = conv.exchange_to_obj(golden_text)
    assert obj_text.count("\nv ") == 8 and obj_text.count("\nf ") == 6
    assert "usemtl Default" in obj_text
    back = conv.obj_to_exchange(obj_text)
    assert back.startswith("VERTICES:8\n") and "POLYGONS:6" in back
    assert "UV:UVMap:24" in back  # 6 quads x 4 corners, all resolved

    # 2. weighted plane: weight/morph sections dropped (no OBJ equivalent)
    golden_text = open(os.path.join(GOLDEN_DIR, "weighted_plane.txt"), encoding="utf-8").read()
    obj_text = conv.exchange_to_obj(golden_text)
    assert "usemtl Checker" in obj_text and obj_text.count("\nf ") == 4

    # 3. OBJ parsing: negative indices, v//vn, comments, ngons
    obj = (
        "# comment\nv 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"
        "vt 0 0\nvt 1 1\n"
        "usemtl Mat A\n"
        "f 1/1 2/2 3/1\n"
        "f -4//1 -2//1 -1//1\n"
        "f 1 2 3 4\n"
    )
    exchange = conv.obj_to_exchange(obj)
    assert "VERTICES:4" in exchange and "POLYGONS:3" in exchange
    assert "0,2,3;;Mat A;;FACE" in exchange  # negative indices resolved
    assert "0,1,2,3;;Mat A;;FACE" in exchange  # ngon preserved

    # 4. CLI end-to-end with OD_CPE_PATH and a fake 1.OBJ next to the script
    workdir = tempfile.mkdtemp(prefix="od_cpe_zbrush_test_")
    plugin_dir = os.path.join(workdir, "plugin")
    os.makedirs(plugin_dir)
    shutil.copyfile(CONVERTER, os.path.join(plugin_dir, "od_zbrush_convert.py"))
    local = load(os.path.join(plugin_dir, "od_zbrush_convert.py"), "od_zbrush_local")
    os.environ["OD_CPE_PATH"] = workdir
    try:
        with open(os.path.join(plugin_dir, "1.OBJ"), "w") as f:
            f.write(obj)
        assert local.main(["export"]) == 0
        assert os.path.exists(os.path.join(workdir, "ODVertexData.txt"))
        os.remove(os.path.join(plugin_dir, "1.OBJ"))
        assert local.main(["import"]) == 0
        assert os.path.exists(os.path.join(plugin_dir, "1.OBJ"))
        assert local.main([]) == 2  # usage error
    finally:
        del os.environ["OD_CPE_PATH"]

    # 5. malformed exchange input raises
    try:
        conv.exchange_to_obj("POLYGONS:1\n0,1,2;;a;;FACE\n")
        raise AssertionError("should have raised")
    except ValueError:
        pass

    print("all zbrush converter tests OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
