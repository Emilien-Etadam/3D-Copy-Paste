# Headless Blender round-trip test for OD_CopyPasteExternal.
#
# For each file in tests/golden/: paste it with the extension's paste
# operator, copy the resulting mesh back with the copy operator, and compare
# the two files semantically (float tolerance; continuous and discontinuous
# UV samples resolved to the same per-polygon-corner mapping; morph "None"
# equivalent to a zero delta).
#
# Run:
#   blender --background --python tests/test_blender_roundtrip.py
# or, with the standalone bpy module (pip install bpy):
#   python3 tests/test_blender_roundtrip.py
#
# Exit code 0 = all golden files round-trip; non-zero otherwise.

import importlib.util
import os
import shutil
import sys
import tempfile

TOL = 1e-5
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(REPO, "tests", "golden")


def load_odformat():
    path = os.path.join(REPO, "Blender", "od_copy_paste_external", "odformat.py")
    spec = importlib.util.spec_from_file_location("odformat", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["odformat"] = module  # dataclasses needs the module registered
    spec.loader.exec_module(module)
    return module


def close(a, b):
    return abs(a - b) <= TOL


def resolve_uvs(mesh, samples):
    """Resolve UV samples to a {(polygon, vertex): (u, v)} mapping.

    Discontinuous samples take precedence over continuous ones, per
    docs/FORMAT.md paragraph 3.5.
    """
    continuous = {}
    discontinuous = {}
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


def compare(golden, output):
    """Compare two ODMesh instances semantically; return a list of errors."""
    errors = []

    if len(golden.vertices) != len(output.vertices):
        return ["vertex count %d != %d" % (len(golden.vertices), len(output.vertices))]
    for i, (gv, ov) in enumerate(zip(golden.vertices, output.vertices)):
        if not all(close(a, b) for a, b in zip(gv, ov)):
            errors.append("vertex %d: %r != %r" % (i, gv, ov))

    if len(golden.polygons) != len(output.polygons):
        return errors + ["polygon count %d != %d" % (len(golden.polygons), len(output.polygons))]
    for i, (gp, op) in enumerate(zip(golden.polygons, output.polygons)):
        if list(gp.indices) != list(op.indices):
            errors.append("polygon %d indices: %r != %r" % (i, gp.indices, op.indices))
        if gp.surface != op.surface:
            errors.append("polygon %d surface: %r != %r" % (i, gp.surface, op.surface))
        if gp.ptype != op.ptype:
            errors.append("polygon %d ptype: %r != %r" % (i, gp.ptype, op.ptype))

    if set(golden.weight_maps) != set(output.weight_maps):
        errors.append(
            "weight maps: %r != %r" % (sorted(golden.weight_maps), sorted(output.weight_maps))
        )
    else:
        for name, gvals in golden.weight_maps.items():
            for i, (g, o) in enumerate(zip(gvals, output.weight_maps[name])):
                if (g is None) != (o is None) or (g is not None and not close(g, o)):
                    errors.append("weight %r vertex %d: %r != %r" % (name, i, g, o))

    if set(golden.morph_maps) != set(output.morph_maps):
        errors.append(
            "morph maps: %r != %r" % (sorted(golden.morph_maps), sorted(output.morph_maps))
        )
    else:
        zero = (0.0, 0.0, 0.0)
        for name, gvals in golden.morph_maps.items():
            for i, (g, o) in enumerate(zip(gvals, output.morph_maps[name])):
                g = g or zero  # "None" means "vertex unaffected", i.e. zero delta
                o = o or zero
                if not all(close(a, b) for a, b in zip(g, o)):
                    errors.append("morph %r vertex %d: %r != %r" % (name, i, g, o))

    if set(golden.uv_maps) != set(output.uv_maps):
        errors.append("UV maps: %r != %r" % (sorted(golden.uv_maps), sorted(output.uv_maps)))
    else:
        for name in golden.uv_maps:
            gres = resolve_uvs(golden, golden.uv_maps[name])
            ores = resolve_uvs(output, output.uv_maps[name])
            if set(gres) != set(ores):
                missing = sorted(set(gres) ^ set(ores))[:5]
                errors.append("UV %r coverage differs (e.g. %r)" % (name, missing))
                continue
            for key in gres:
                if not all(close(a, b) for a, b in zip(gres[key], ores[key])):
                    errors.append("UV %r %r: %r != %r" % (name, key, gres[key], ores[key]))

    return errors


def clear_scene(bpy):
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)


def main():
    try:
        import bpy
    except ImportError:
        print("FAIL: bpy unavailable — run via: blender --background --python %s" % __file__)
        return 2

    sys.path.insert(0, os.path.join(REPO, "Blender"))
    import od_copy_paste_external as extension

    extension.register()
    odformat = load_odformat()

    workdir = tempfile.mkdtemp(prefix="od_cpe_test_")
    os.environ["OD_CPE_PATH"] = workdir
    exchange = os.path.join(workdir, "ODVertexData.txt")

    golden_files = sorted(
        f for f in os.listdir(GOLDEN_DIR) if f.endswith(".txt")
    )
    if not golden_files:
        print("FAIL: no golden files in %s" % GOLDEN_DIR)
        return 2

    failures = 0
    for name in golden_files:
        golden_path = os.path.join(GOLDEN_DIR, name)
        clear_scene(bpy)
        shutil.copyfile(golden_path, exchange)
        try:
            result = bpy.ops.object.od_paste_from_external()
            if result != {'FINISHED'}:
                raise RuntimeError("paste returned %r" % result)
            result = bpy.ops.object.od_copy_to_external()
            if result != {'FINISHED'}:
                raise RuntimeError("copy returned %r" % result)
        except Exception as exc:
            print("FAIL %s: operator error: %s" % (name, exc))
            failures += 1
            continue

        with open(golden_path, "r", encoding="utf-8") as f:
            golden = odformat.parse(f.read())
        with open(exchange, "r", encoding="utf-8") as f:
            output = odformat.parse(f.read())
        errors = compare(golden, output)
        if errors:
            failures += 1
            print("FAIL %s (%d differences):" % (name, len(errors)))
            for error in errors[:20]:
                print("  - " + error)
        else:
            print(
                "PASS %s (%d verts, %d polys, %d weight, %d morph, %d UV maps)"
                % (
                    name,
                    len(golden.vertices),
                    len(golden.polygons),
                    len(golden.weight_maps),
                    len(golden.morph_maps),
                    len(golden.uv_maps),
                )
            )

    print("%d/%d golden files round-trip OK" % (len(golden_files) - failures, len(golden_files)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
