# OD_CopyPasteExternal

Copy and paste mesh geometry between 3D applications through a simple ASCII
exchange file — no export dialogs, no file management. Copy in one
application, paste in another; vertices, polygons, materials, UV maps,
weight maps and morphs travel along where the host application supports
them.

This repository is a **maintained fork** of
[heimlich1024/OD_CopyPasteExternal](https://github.com/heimlich1024/OD_CopyPasteExternal)
by Oliver Hotz (Apache 2.0), which is no longer developed. The fork is a
full revival: **twelve live integrations** (Blender, Rhino, Maya, Houdini,
Cinema 4D, 3ds Max, ZBrush, SketchUp, Moi3D — all rewritten or repaired —
plus new Plasticity, SolidWorks and Godot support and universal OBJ tools),
a normative specification of the interchange format, **twelve CI test
suites**, and **no compiled binaries** anywhere (the antivirus-flagged
`.exe` converters are gone). Implementations for discontinued applications
(XSI, Modo, Lightwave) were removed — files they wrote still paste
correctly everywhere.

**Latest release:**
[v3.0.0](https://github.com/Emilien-Etadam/3D-Copy-Paste/releases/latest) —
includes the installable Blender extension zip; every other integration
installs from this repository (see each application's README below).

## How it works

Every implementation reads and writes the same file, `ODVertexData.txt`, in
the system temp directory (all applications on one machine resolve the same
location, so copy/paste works with zero configuration). Set the
**`OD_CPE_PATH`** environment variable to a directory to relocate the file —
e.g. a network share or synced folder to exchange geometry between machines.
All maintained implementations honor it (Blender also exposes it as an
add-on preference; Moi3D uses an in-script variable, as its engine cannot
read the environment).

The file format is fully specified in **[docs/FORMAT.md](docs/FORMAT.md)**:
plain ASCII, forward-extensible sections, 0-based indices, OBJ coordinate
conventions. Files written by any historical implementation still paste
correctly — backward compatibility is a hard requirement of this fork.

CAD applications additionally share the **`ODSolidData.x_t` Parasolid
side-channel** (FORMAT.md §7): same location and copy/paste semantics, but
carrying exact B-rep geometry — SolidWorks ↔ Plasticity with zero
tessellation.

## Maintained implementations

| Application | Where | Data | Notes |
|---|---|---|---|
| **Blender 4.2+ LTS** | [`Blender/`](Blender/) | verts, polys (n-gons), materials, UVs, weights, morphs (shape keys) | Extension format (`blender_manifest.toml`); install from zip. See [`Blender/README.md`](Blender/README.md) |
| **Rhino 8** | [`Rhino/`](Rhino/) | verts, polys (n-gons via Rhino ngons), materials on copy, UVs, model-unit conversion | CPython ScriptEditor scripts; Breps copy through their render mesh with a warning. See [`Rhino/README.md`](Rhino/README.md) |
| **Maya 2022+** | [`Maya/`](Maya/) | verts, polys (n-gons), materials, UV sets, skin weights (copy), blend shapes, cm/m conversion | OpenMaya 2.0 rewrite. See [`Maya/README.md`](Maya/README.md) |
| **Houdini** | [`Houdini/`](Houdini/) | verts, polys, weights, UVs | Legacy shelf tools with targeted fixes (Python 3 paste, shared temp path) |
| **Any OBJ application** | [`tools/`](tools/) | verts, polys (n-gons), materials, UVs | Cross-platform `od_obj.py` CLI + `od_watch.py` live OBJ mirror — Plasticity, Light Tracer Render, ZBrush/Substance/3D-Coat workflows. See [`tools/README.md`](tools/README.md) |
| **Plasticity** | [`Plasticity/`](Plasticity/) | verts, triangles, per-object surfaces | Live copy via the bridge WebSocket (`plasticity_copy.py --watch`), paste via OBJ. See [`Plasticity/README.md`](Plasticity/README.md) |
| **SolidWorks** | [`SolidWorks/`](SolidWorks/) | exact B-rep via the `ODSolidData.x_t` Parasolid side-channel | VBA copy/paste macros; pairs natively with Plasticity. See [`SolidWorks/README.md`](SolidWorks/README.md) |
| **Godot 4.4+** | [`Godot/`](Godot/) | verts, triangles (n-gon fan), surfaces/materials, UVs | Editor addon, Tool-menu commands, CI-tested headless. See [`Godot/README.md`](Godot/README.md) |
| **Cinema 4D R23+** | [`C4D/`](C4D/) | verts, polys (n-gon fan), materials, UVs, weight maps (Vertex Map tags) | Native Python scripts, no OBJ dialog. See [`C4D/README.md`](C4D/README.md) |
| **3ds Max 2021+** | [`3DSMax/`](3DSMax/) | verts, triangles, materials (MultiMaterial), UVs, unit conversion | pymxs scripts (MaxPlus is gone). See [`3DSMax/README.md`](3DSMax/README.md) |
| **ZBrush 2021+** | [`ZBrush/`](ZBrush/) | verts, polys (n-gons), surface names, UVs (via OBJ) | ZScript + cross-platform Python converter (no more flagged `.exe`). See [`ZBrush/README.md`](ZBrush/README.md) |
| **SketchUp 2017+** | [`Sketchup/`](Sketchup/) | verts, faces (n-gons), materials, UVs, inch/meter conversion | Full Ruby extension (copy **and** paste). See [`Sketchup/README.md`](Sketchup/README.md) |
| **Moi3D** | [`Moi3D/`](Moi3D/) | verts, polys (n-gons), surface names, UVs (via native OBJ) | Pure JScript, no more `.exe` converters. See [`Moi3D/README.md`](Moi3D/README.md) |

Substance Painter, 3D-Coat and Unity still work as shipped upstream and live
**unmodified** in [`legacy/`](legacy/) — the cross-platform
[`tools/od_obj.py`](tools/) converter replaces their compiled `.exe` route.
See [`legacy/README.md`](legacy/README.md).
Implementations for discontinued applications (XSI, Modo, Lightwave) were
removed in July 2026 and remain available in git history.

## Documentation

* [docs/FORMAT.md](docs/FORMAT.md) — the interchange format specification
  (normative), with an annotated example and a conformance checklist.
* [docs/AUDIT.md](docs/AUDIT.md) — audit of all historical implementations:
  findings F1–F16, upstream issues and PR history.
* [docs/TESTING.md](docs/TESTING.md) — the automated tests and nine manual
  checklists (Rhino, Maya, C4D, 3ds Max, SketchUp, ZBrush, Moi3D,
  Plasticity, SolidWorks) plus cross-application spot checks.

## Testing

Twelve suites run in CI on every pull request:

* **Real-application round-trips** — Blender 4.2 (standalone `bpy` module)
  and Godot 4.4 (headless binary) paste the golden files, copy them back
  and compare geometrically.
* **Unit suites** — the format module, the OBJ/ZBrush/Moi3D converters
  (Python, Node), the SketchUp logic (Ruby), and mocked-API tests for the
  Rhino, Maya, C4D and 3ds Max scripts.

```
python3 tests/test_odformat.py                                  # format spec
python3 tests/test_blender_roundtrip.py                         # needs: pip install "bpy==4.2.*"
godot --headless --path Godot --script res://tests/roundtrip_test.gd
ruby tests/test_sketchup_logic.rb
node tests/test_moi3d_logic.js
```

CI also packages the installable Blender extension zip on every pull
request, and the [release workflow](.github/workflows/release.yml)
publishes it on `v*` tags (or manual dispatch).

## Credits & license

Original project and format by **Oliver Hotz** (Origami Digital), with
contributions from the upstream community. Licensed under the
[Apache License 2.0](LICENSE), unchanged in this fork.
