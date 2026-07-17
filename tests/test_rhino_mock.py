# Unit tests for the Rhino 8 scripts, runnable without Rhino.
#
# RhinoCommon (Rhino, scriptcontext, System) is replaced by lightweight
# fakes, then the two scripts are imported as modules and their pure logic
# is exercised: a full copy -> file -> paste round-trip in a millimeter
# document (axis mapping and unit scaling verified numerically), the golden
# files, n-gon fan + Rhino ngon grouping, degenerate legacy quads, and
# malformed-file error paths.
#
# Run: python3 tests/test_rhino_mock.py
# What the fakes cannot prove — real RhinoCommon API behavior, document
# interaction, the GetObject prompt — is covered by the manual checklist in
# docs/TESTING.md.

import importlib.util
import os
import sys
import tempfile
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(REPO, "tests", "golden")


# ---- fake RhinoCommon ------------------------------------------------------

class FakePoint:
    def __init__(self, x, y, z=0.0):
        self.X, self.Y, self.Z = x, y, z


class FakeList:
    def __init__(self):
        self._items = []

    def Add(self, *args):
        self._items.append(FakePoint(*args))
        return len(self._items) - 1

    @property
    def Count(self):
        return len(self._items)

    def __getitem__(self, i):
        return self._items[i]


class FakeFace:
    def __init__(self, corners):
        self.A, self.B, self.C = corners[:3]
        self.D = corners[3] if len(corners) == 4 else corners[2]
        self.IsQuad = len(corners) == 4


class FakeFaces(FakeList):
    def AddFace(self, *idx):
        self._items.append(FakeFace(list(idx)))
        return len(self._items) - 1


class FakeNgons:
    def __init__(self):
        self.added = []

    def AddNgon(self, ngon):
        self.added.append(ngon)


class FakeMesh:
    def __init__(self):
        self.Vertices = FakeList()
        self.Faces = FakeFaces()
        self.TextureCoordinates = FakeList()
        self.Ngons = FakeNgons()
        self.Normals = types.SimpleNamespace(ComputeNormals=lambda: None)
        self.IsValid = True

    def Compact(self):
        pass


def install_fakes():
    logged = []
    rhino = types.ModuleType("Rhino")
    rhino.RhinoApp = types.SimpleNamespace(WriteLine=logged.append)
    # meters <-> millimeters in both directions
    rhino.RhinoMath = types.SimpleNamespace(
        UnitScale=lambda src, dst: 0.001 if dst == "meters" else 1000.0
    )
    rhino.UnitSystem = types.SimpleNamespace(Meters="meters")
    rhino.Geometry = types.SimpleNamespace(
        Mesh=FakeMesh,
        MeshType=types.SimpleNamespace(Render="render"),
        MeshNgon=types.SimpleNamespace(
            Create=lambda verts, faces: ("ngon", list(verts), list(faces))
        ),
    )
    rhino.Input = types.SimpleNamespace(Custom=types.SimpleNamespace(GetObject=None))
    rhino.DocObjects = types.SimpleNamespace(
        ObjectType=types.SimpleNamespace(Mesh=1, Brep=2, Extrusion=4, SubD=8)
    )
    rhino.Commands = types.SimpleNamespace(Result=types.SimpleNamespace(Success=0))

    selection = []
    doc = types.SimpleNamespace(
        ModelUnitSystem="mm",
        Objects=types.SimpleNamespace(
            GetSelectedObjects=lambda a, b: iter(selection),
            AddMesh=lambda mesh, attrs: "guid-1",
            Select=lambda guid: True,
        ),
        Views=types.SimpleNamespace(Redraw=lambda: None),
        CreateDefaultAttributes=lambda: types.SimpleNamespace(Name=None),
    )
    sc = types.ModuleType("scriptcontext")
    sc.doc = doc
    system = types.ModuleType("System")
    system.Guid = types.SimpleNamespace(Empty="guid-empty")

    sys.modules["Rhino"] = rhino
    sys.modules["scriptcontext"] = sc
    sys.modules["System"] = system
    return logged, selection


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    logged, selection = install_fakes()
    copy_mod = load(os.path.join(REPO, "Rhino", "Rhino_CopyToExternal.py"), "rhino_copy")
    paste_mod = load(os.path.join(REPO, "Rhino", "Rhino_PasteFromExternal.py"), "rhino_paste")

    workdir = tempfile.mkdtemp(prefix="od_cpe_rhino_test_")
    saved_env = os.environ.get("OD_CPE_PATH")
    os.environ["OD_CPE_PATH"] = workdir
    try:
        run_tests(copy_mod, paste_mod, logged, selection, workdir)
    finally:
        if saved_env is None:
            os.environ.pop("OD_CPE_PATH", None)
        else:
            os.environ["OD_CPE_PATH"] = saved_env
    print("all rhino mock tests OK (%d console messages)" % len(logged))
    return 0


def run_tests(copy_mod, paste_mod, logged, selection, workdir):
    # 1. copy: fake 1 m cube in a mm document, quads + texture coordinates
    mesh = FakeMesh()
    cube = [(-500, -500, -500), (-500, -500, 500), (-500, 500, 500), (-500, 500, -500),
            (500, -500, -500), (500, -500, 500), (500, 500, 500), (500, 500, -500)]
    for p in cube:
        mesh.Vertices.Add(*p)
    for q in [(0, 1, 2, 3), (0, 4, 5, 1), (1, 5, 6, 2),
              (3, 2, 6, 7), (0, 3, 7, 4), (4, 7, 6, 5)]:
        mesh.Faces.AddFace(*q)
    for i in range(8):
        mesh.TextureCoordinates.Add(i / 10.0, i / 20.0)
    selection.append(types.SimpleNamespace(
        Name="box", Id="id-1", Geometry=mesh,
        GetMaterial=lambda front: types.SimpleNamespace(Name="Steel"),
    ))

    copy_mod.copy_to_external()
    path = os.path.join(workdir, "ODVertexData.txt")
    text = open(path, encoding="utf-8").read()
    assert text.startswith("VERTICES:8\n"), text[:40]
    assert "POLYGONS:6" in text and ";;Steel;;FACE" in text
    assert "UV:UVMap:24" in text

    # 2. paste it back: mm document => x1000, axis round-trip must be exact
    data = paste_mod.parse(text)
    assert len(data["vertices"]) == 8 and len(data["polygons"]) == 6
    out = paste_mod.build_mesh(data, 1000.0)
    v0 = out.Vertices[0]
    assert (round(v0.X), round(v0.Y), round(v0.Z)) == (-500, -500, -500)
    assert out.Faces.Count == 6 and out.Faces[0].IsQuad
    assert out.TextureCoordinates.Count == 8
    assert abs(out.TextureCoordinates[3].X - 0.3) < 1e-9

    # 3. golden files parse and build (mixed UV forms, weights/morphs skipped)
    golden = open(os.path.join(GOLDEN_DIR, "cube_uv.txt"), encoding="utf-8").read()
    data = paste_mod.parse(golden)
    out = paste_mod.build_mesh(data, 1.0)
    assert out.Vertices.Count == 8 and out.Faces.Count == 6
    assert out.TextureCoordinates.Count == 8

    golden = open(os.path.join(GOLDEN_DIR, "weighted_plane.txt"), encoding="utf-8").read()
    data = paste_mod.parse(golden)
    assert data["ignored"] == ["edge_falloff", "left_side", "bump"]
    out = paste_mod.build_mesh(data, 1.0)
    assert out.Vertices.Count == 9 and out.Faces.Count == 4

    # 4. n-gon fan + Rhino ngon grouping; degenerate legacy quad; SUBD note
    ngon_file = (
        "VERTICES:7\n0 0 0\n1 0 0\n2 1 0\n1 2 0\n0 2 0\n-1 1 0\n5 5 5\n"
        "POLYGONS:3\n0,1,2,3,4,5;;Default;;FACE\n0,1,2,2;;Default;;FACE\n"
        "0,1,1;;Default;;SUBD\n"
    )
    data = paste_mod.parse(ngon_file)
    out = paste_mod.build_mesh(data, 1.0)
    # hexagon -> 4 fan triangles + 1 triangle from the degenerate quad;
    # the 2-unique-vertex polygon is dropped
    assert out.Faces.Count == 5, out.Faces.Count
    assert len(out.Ngons.added) == 1 and out.Ngons.added[0][1] == [0, 1, 2, 3, 4, 5]
    assert any("SUBD/CCSS" in message for message in logged)

    # 5. malformed input must raise, not crash later
    for bad in [
        "POLYGONS:1\n0,1,2;;a;;FACE\n",                       # no VERTICES
        "VERTICES:2\n0 0 0\n",                                # truncated
        "VERTICES:3\n0 0 0\n1 0 0\n0 1 0\nPOLYGONS:1\n0,1,9;;a;;FACE\n",  # bad index
    ]:
        try:
            paste_mod.parse(bad)
            raise AssertionError("should have raised: %r" % bad)
        except ValueError:
            pass


if __name__ == "__main__":
    sys.exit(main())
