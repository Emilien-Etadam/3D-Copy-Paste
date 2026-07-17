# OD_CopyPasteExternal

Copy and paste mesh geometry between 3D applications through a simple ASCII
exchange file — no export dialogs, no file management. Copy in one
application, paste in another; vertices, polygons, materials, UV maps,
weight maps and morphs travel along where the host application supports
them.

This repository is a **maintained fork** of
[heimlich1024/OD_CopyPasteExternal](https://github.com/heimlich1024/OD_CopyPasteExternal)
by Oliver Hotz (Apache 2.0), which is no longer developed. The fork
modernizes the implementations application by application (Blender, Rhino
and Maya are rewritten; Houdini is fixed; C4D, 3ds Max, ZBrush, Sketchup and
Moi3D repairs are on the roadmap, along with new Plasticity, SolidWorks,
Godot and Light Tracer integrations), documents the interchange format, and
keeps the not-yet-repaired implementations as-is under [`legacy/`](legacy/).
Implementations for discontinued applications (XSI, Modo, Lightwave) were
removed — files they wrote still paste correctly everywhere.

## How it works

Every implementation reads and writes the same file, `ODVertexData.txt`, in
the system temp directory (all applications on one machine resolve the same
location, so copy/paste works with zero configuration). Set the
**`OD_CPE_PATH`** environment variable to a directory to relocate the file —
e.g. a network share or synced folder to exchange geometry between machines
(supported by the Blender and Rhino implementations).

The file format is fully specified in **[docs/FORMAT.md](docs/FORMAT.md)**:
plain ASCII, forward-extensible sections, 0-based indices, OBJ coordinate
conventions. Files written by any historical implementation still paste
correctly — backward compatibility is a hard requirement of this fork.

## Maintained implementations

| Application | Where | Data | Notes |
|---|---|---|---|
| **Blender 4.2+ LTS** | [`Blender/`](Blender/) | verts, polys (n-gons), materials, UVs, weights, morphs (shape keys) | Extension format (`blender_manifest.toml`); install from zip. See [`Blender/README.md`](Blender/README.md) |
| **Rhino 8** | [`Rhino/`](Rhino/) | verts, polys (n-gons via Rhino ngons), materials on copy, UVs, model-unit conversion | CPython ScriptEditor scripts; Breps copy through their render mesh with a warning. See [`Rhino/README.md`](Rhino/README.md) |
| **Maya** | [`Maya/`](Maya/) | verts, polys, weights (vertex colors) | Legacy scripts with targeted fixes (valid headers, Python 3, spec-conformant axes) |
| **Houdini** | [`Houdini/`](Houdini/) | verts, polys, weights, UVs | Legacy shelf tools with targeted fixes (Python 3 paste, shared temp path) |
| **Any OBJ application** | [`tools/`](tools/) | verts, polys (n-gons), materials, UVs | Cross-platform `od_obj.py` CLI + `od_watch.py` live OBJ mirror — Plasticity, Light Tracer Render, ZBrush/Substance/3D-Coat workflows. See [`tools/README.md`](tools/README.md) |
| **Plasticity** | [`Plasticity/`](Plasticity/) | verts, triangles, per-object surfaces | Live copy via the bridge WebSocket (`plasticity_copy.py --watch`), paste via OBJ. See [`Plasticity/README.md`](Plasticity/README.md) |
| **SolidWorks** | [`SolidWorks/`](SolidWorks/) | exact B-rep via the `ODSolidData.x_t` Parasolid side-channel | VBA copy/paste macros; pairs natively with Plasticity. See [`SolidWorks/README.md`](SolidWorks/README.md) |
| **Godot 4.4+** | [`Godot/`](Godot/) | verts, triangles (n-gon fan), surfaces/materials, UVs | Editor addon, Tool-menu commands, CI-tested headless. See [`Godot/README.md`](Godot/README.md) |

Everything else (ZBrush, C4D, 3ds Max, Sketchup, Moi3D, Substance Painter,
3D-Coat, Unity) lives **unmodified** in [`legacy/`](legacy/) pending repair —
see [`legacy/README.md`](legacy/README.md) for the state and plan of each.
Implementations for discontinued applications (XSI, Modo, Lightwave) were
removed in July 2026 and remain available in git history.

## Documentation

* [docs/FORMAT.md](docs/FORMAT.md) — the interchange format specification
  (normative), with an annotated example and a conformance checklist.
* [docs/AUDIT.md](docs/AUDIT.md) — audit of all historical implementations:
  findings F1–F16, upstream issues and PR history.
* [docs/TESTING.md](docs/TESTING.md) — automated Blender round-trip test and
  the manual checklists (Rhino 8, Blender, cross-application).

## Testing

```
python3 tests/test_odformat.py                              # format unit tests
blender --background --python tests/test_blender_roundtrip.py   # round-trip
```

The round-trip test also runs without a Blender install via the standalone
bpy module (`pip install "bpy==4.2.*"`, Python 3.11). Both run in CI on every
pull request, and CI publishes the installable Blender extension zip as a
build artifact.

## Credits & license

Original project and format by **Oliver Hotz** (Origami Digital), with
contributions from the upstream community. Licensed under the
[Apache License 2.0](LICENSE), unchanged in this fork.
