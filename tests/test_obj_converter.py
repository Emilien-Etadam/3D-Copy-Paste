# Unit tests for tools/od_obj.py (OBJ <-> ODVertexData converter).
#
# Run: python3 tests/test_obj_converter.py

import importlib.util
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(REPO, "tests", "golden")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


od_obj = load(os.path.join(REPO, "tools", "od_obj.py"), "od_obj")
odformat = od_obj.odformat


def resolve_uvs(mesh, samples):
    continuous, discontinuous = {}, {}
    for s in samples:
        if s.polygon is None:
            continuous[s.vertex] = (s.u, s.v)
        else:
            discontinuous[(s.polygon, s.vertex)] = (s.u, s.v)
    resolved = {}
    for p, poly in enumerate(mesh.polygons):
        for v in poly.indices:
            uv = discontinuous.get((p, v), continuous.get(v))
            if uv is not None:
                resolved[(p, v)] = uv
    return resolved


def main():
    # 1. golden cube -> OBJ -> back: geometry, surfaces and resolved UVs equal
    golden_text = open(os.path.join(GOLDEN_DIR, "cube_uv.txt"), encoding="utf-8").read()
    golden = odformat.parse(golden_text)
    obj_text, dropped = od_obj.odmesh_to_obj(golden)
    assert dropped == []
    back = od_obj.obj_to_odmesh(obj_text)
    assert back.vertices == golden.vertices
    assert [p.indices for p in back.polygons] == [p.indices for p in golden.polygons]
    assert [p.surface for p in back.polygons] == [p.surface for p in golden.polygons]
    g_uv = resolve_uvs(golden, golden.uv_maps["txuvmap"])
    b_uv = resolve_uvs(back, back.uv_maps["UVMap"])
    assert g_uv == b_uv, "resolved UVs differ after OBJ round-trip"

    # 2. weighted plane -> OBJ drops weight/morph maps with a notice
    golden = odformat.parse(
        open(os.path.join(GOLDEN_DIR, "weighted_plane.txt"), encoding="utf-8").read()
    )
    obj_text, dropped = od_obj.odmesh_to_obj(golden)
    assert dropped == ["edge_falloff", "left_side", "bump"] or set(dropped) == {
        "edge_falloff", "left_side", "bump"
    }
    assert "usemtl Checker" in obj_text

    # 3. OBJ parsing details: negative indices, v//vn corners, comments, ngons
    obj = (
        "# comment\n"
        "o test\n"
        "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nv 0.5 2 0\n"
        "vt 0 0\nvt 1 0\nvt 1 1\n"
        "usemtl Mat A\n"
        "f 1/1 2/2 3/3\n"
        "f -5//1 -3//1 -1//1\n"          # negative vertex indices, no vt
        "f 1 2 3 4 5\n"                   # ngon, no vt
    )
    mesh = od_obj.obj_to_odmesh(obj)
    assert len(mesh.vertices) == 5 and len(mesh.polygons) == 3
    assert mesh.polygons[0].surface == "Mat A"
    assert mesh.polygons[1].indices == [0, 2, 4]
    assert mesh.polygons[2].indices == [0, 1, 2, 3, 4]
    samples = mesh.uv_maps["UVMap"]
    assert len(samples) == 3 and samples[0].polygon == 0 and samples[0].vertex == 0

    # 4. converted output is valid exchange-file text (serialize + reparse)
    reparsed = odformat.parse(odformat.serialize(mesh))
    assert len(reparsed.polygons) == 3

    # 5. CLI end-to-end in a temp dir via OD_CPE_PATH
    workdir = tempfile.mkdtemp(prefix="od_cpe_obj_test_")
    env = dict(os.environ, OD_CPE_PATH=workdir)
    obj_in = os.path.join(workdir, "in.obj")
    with open(obj_in, "w") as f:
        f.write(obj)
    tool = os.path.join(REPO, "tools", "od_obj.py")
    subprocess.run([sys.executable, tool, "--from-obj", obj_in], check=True, env=env,
                   capture_output=True)
    assert os.path.exists(os.path.join(workdir, "ODVertexData.txt"))
    result = subprocess.run([sys.executable, tool, "--to-obj"], check=True, env=env,
                            capture_output=True, text=True)
    out_obj = os.path.join(workdir, "OD_CPE.obj")
    assert os.path.exists(out_obj), result.stdout
    assert "f " in open(out_obj).read()

    print("all obj converter tests OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
