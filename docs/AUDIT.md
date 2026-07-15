# Phase 0 audit — OD_CopyPasteExternal fork

Audit date: 2026-07-15. Baseline: fork of `heimlich1024/OD_CopyPasteExternal`
at upstream head `858c4c7` ("Fix for Blender 3.x as well as Houdini 19 (py3
adjustment)", May 2022). Upstream is abandoned. The interchange format itself
is specified in [`docs/FORMAT.md`](FORMAT.md); this document records the state
of each implementation, the bugs/deviations found while reverse-engineering
the format, and the upstream issues that relate to them.

## 1. Implementation inventory

| App | Copy | Paste | Sections handled | Runtime | Status |
|---|---|---|---|---|---|
| Modo (kit) | yes | yes | verts, polys (FACE/SUBD/CCSS), weights, morphs, UVs, vertex normals | Modo Python (py2-era kit) | Reference writer; paste has bugs (F7, F8). Broken on Modo 16.1+/py3 (#71) |
| Lightwave | yes | yes (Modeler + Layout) | verts, polys (FACE/SUBD/CCSS), weights, morphs, UVs, vertex normals (write-only) | LW PCore Python 2 | Works on LW 2015–2019; py2 only |
| Blender (`Blender310/`) | yes | yes | verts, polys (FACE only), weights, morphs (shape keys), UVs | Blender ≥3.0 Python | Copy works on 3.x; paste partially broken (F4, F5); both broken on 4.x (F5) |
| Blender (`Blender280/`, `Blender290/`, root) | yes | yes | same | Blender 2.7x–2.9x | Historical versions, superseded |
| Rhino | stub | stub | verts, polys only | IronPython 2 (Rhino 5–7) | Unfinished upstream stub (F10) |
| Houdini | yes | yes | verts, polys, weights (float point attrs), UVs | shelf tool creating embedded Python SOP | Copy fixed for py3 in `858c4c7`; **paste still py2-only** (F3) |
| Maya | yes | yes | verts, polys, "weights" via vertex color red channel | maya.cmds, py2-era | Copy writes a corrupt header when the scene is saved (F1) |
| 3ds Max | yes | yes | verts, polys | MaxPlus Python 2 | MaxPlus removed in Max 2020+; broken (#56) |
| C4D | via OBJ | via OBJ | verts, polys, UVs | Python scripts wrapping an OBJ export/import dialog | Broken on R23+ (#57, #66) |
| XSI | yes | yes | verts, polys, weights, morphs | XSI Python | Frozen (XSI discontinued) |
| Sketchup | no | yes | verts, polys | Ruby console script | Paste-only starting point |
| Moi3D | yes | yes | verts, polys | JS + compiled `objToVertData.exe`/`vertDataToObj.exe` | Windows-only binaries |
| ZBrush | yes | yes | verts, polys, UVs | ZScript + compiled exe converters | Windows/OSX binaries; export broken since ZBrush 2021.7 (#59) |
| Substance Painter | — | yes | verts, polys, UVs | QML + compiled exe | Windows-only |
| 3D-Coat | yes | yes | verts, polys, UVs | 3D-Coat script + compiled exe | Windows-only |
| Unity | yes | yes | verts, polys, UVs, weights, materials | C# editor scripts | Assumes left-handed coords on import (upstream README note) |

The OBJ-converter family (C4D, Moi3D, ZBrush, Substance, 3D-Coat) shares the
sources in `docs/objToVertData.py` / `docs/vertDataToObj.py`, distributed as
PyInstaller Windows binaries checked into the repo.

## 2. Findings (format bugs, deviations, hazards)

Numbered for reference from commits and later phases.

* **F1 — Maya copy writes a corrupt first line.** `maya_ExportToExternal.py`
  writes the scene name immediately before `VERTICES:` with no newline
  (`f.write(sname); f.write("VERTICES:")`). With a saved scene the first line
  becomes `<scenepath>VERTICES:8`, which no parser recognizes — every paste
  sees an empty file. Only unsaved scenes produce valid files. (Related
  upstream: #62, #70.)
* **F2 — Houdini uses a different file path.** Both Houdini scripts use
  `tempfile.gettempdir() + os.sep + ".." + os.sep + "ODVertexData.txt"`. This
  compensates for Houdini's private `%TEMP%\houdini_temp` on Windows, but on
  Linux/macOS it resolves to the *parent* of the shared temp dir (e.g. `/`),
  so Houdini and every other app read/write different files.
* **F3 — Houdini paste is still Python 2.** Upstream `858c4c7` converted only
  the copy script; `Houdini_PasteFromExternal.py` still uses `xrange` inside
  the embedded SOP code and fails on Houdini 18.5+ default py3 builds. This is
  the actual cause of open issues #64 (Houdini part) and #65.
* **F4 — Blender paste mis-applies UVs.** The UV loop assigns sample *N* to
  loop `count % len(face.loops)` of the polygon named in the line, ignoring
  the `PNT` vertex index, and silently drops continuous-form lines
  (`else: pass`). It only works for files whose samples are written in exact
  polygon/loop order (Blender's and Modo's own output). Lightwave files
  (discontinuous-then-continuous ordering) and Houdini files (reversed
  per-poly sample order, F13) paste with scrambled or missing UVs.
* **F5 — Blender paste uses APIs removed in modern Blender.**
  `obj.vertex_groups.new(name)` positional argument (keyword-only since 2.8),
  `bpy.ops.object.material_slot_remove({'object': obj})` context-override
  dict (removed in 4.0), unguarded `bpy.ops` mode switches requiring specific
  context. The paste also recomputes an unused `vgroups` dict and calls
  `mesh.update()` twice. Target of Phase 1.
* **F6 — Two incompatible `VERTEXNORMALS` dialects.** Lightwave and the OBJ
  converter write `VERTEXNORMALS:<count>` with bare `x y z` lines; Modo
  writes `VERTEXNORMALS:VertexNormals:<count>` with `x y z:PLY:p:PNT:v`
  lines. Modo's paste reads the count from the third `:`-field and indexes
  `PLY`/`PNT` fields, so it crashes or misparses Lightwave-dialect files.
  Neither dialect matches the informal `docs/datafile.txt` description.
  FORMAT.md deprecates the section.
* **F7 — Modo paste assumes a vertex-normal map exists.** After the mesh
  edit it unconditionally runs
  `select.vertexMap <maps[0].name>` on `getMapsByType(i_VMAP_NORMAL)`; for
  files without a `VERTEXNORMALS` section (Blender, Rhino, Maya, OBJ
  converters…) the list is empty and the paste errors after building the
  mesh.
* **F8 — Modo morph paste assumes `VERTICES` starts at line 0.** It rebuilds
  absolute morph positions by reading base coordinates from `lines[i + 1]`
  (file-absolute), not from the recorded `VERTICES` offset. Valid only when
  `VERTICES:` is the first line of the file — which FORMAT.md therefore
  mandates for writers.
* **F9 — Inconsistent "no value" encoding.** Modo writes `None` for
  unassigned weight/morph vertices; Lightwave writes `0.0` (weights) and
  `0 0 0` (morphs); Blender writes explicit values for all vertices. Readers
  must accept both `None` and numeric forms; semantics differ (unassigned vs
  zero) and cannot be recovered from Lightwave files.
* **F10 — Rhino scripts are unfinished stubs.** Copy uses
  `rhinoscriptsyntax`, exports no UVs/weights/materials, and de-duplicates
  repeated vertex indices in `MeshFaceVertices` quads (Rhino encodes a
  triangle as a quad with a repeated corner) by *string* comparison of the
  whole face. Paste builds only tri/quad faces (n-gons are silently dropped),
  ignores UV/weight/morph sections and polytype, and is IronPython-2-only
  (`xrange`). Replaced wholesale in Phase 2.
* **F11 — Informal docs drift from the code.** `docs/datafile.txt` documents
  the UV lines without the literal `PLY:`/`PNT:` tags and `VERTEXNORMALS`
  with a single argument; the upstream README calls the file
  `ODVertData.txt`. All 16 implementations write `ODVertexData.txt` and the
  tagged UV forms. `docs/FORMAT.md` is now the normative spec;
  `datafile.txt`/`datafile_example.txt` are kept as historical artifacts.
* **F12 — Blender copy exports dense weights.** Every vertex gets an explicit
  value (0.0 for unassigned), losing the assigned/unassigned distinction that
  Modo/LW preserve via `None`. Harmless for round-trips but asymmetric.
* **F13 — Houdini copy scrambles UV sample order.** Polygon vertex lists are
  reversed-then-rotated for winding conversion, but UV samples are emitted in
  plain reversed traversal order. `PLY`/`PNT` indices are correct, so
  spec-compliant readers are fine, but order-dependent readers (Blender
  paste, F4) get wrong UVs — the likely cause of "UVs broken between Houdini
  and Blender" reports.
* **F14 — Multiple `VERTICES`/`POLYGONS` blocks are unspecified.** Parsers
  collect headers into lists as if multiple meshes were supported, but e.g.
  Blender's paste keeps only the last block's vertices while indexing
  polygons over all blocks. FORMAT.md mandates exactly one of each.
* **F15 — Compiled converter binaries embed a UV ordering hack.**
  `vertDataToObj.py` (shipped as `.exe`) rebuilds per-face `vt` assignments
  with a reversed index lookup (`testidx[len(testpts)-1-t]`) and sorts the UV
  value list, which only round-trips for the OBJ files its sibling produced.
  The binaries are Windows-only and unbuildable from CI (PyInstaller, py2).

## 3. Upstream open issues (as of 2026-07-15)

| # | Title | Relevance to this fork |
|---|---|---|
| [#71](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/71) | od_C/P needs update for Modo 17 | Modo kit is py2; Modo 16.1+ ship py3. Out of scope — Modo moves to `legacy/` unmodified |
| [#70](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/70) | Maya 2024/2025 support? | Maya scripts are py2-era + F1. Not covered by current phases |
| [#69](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/69) | Copying Curves data | Feature request; format has no curve section. Out of scope |
| [#68](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/68) | Any interest in Godot Engine? | Feature request; out of scope |
| [#67](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/67) | Meshing options | Feature request (NURBS meshing control). Phase 2's Rhino copy touches this: render mesh is used with an explicit warning |
| [#66](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/66) | Doesn't work with C4D | C4D OBJ-dialog wrapper broken on modern C4D. Out of scope — `legacy/` |
| [#65](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/65) | PasteFromExternal doesn't work in Houdini 19 | Root cause F3 (paste still py2); upstream fix only converted the copy script. Not covered by current phases (Houdini untouched) — documented here |
| [#64](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/64) | Not working: Blender 3.0, Houdini 19, ZBrush 2022 | Blender copy crash (no shape keys) fixed upstream in `858c4c7`; Blender paste issues remain (F4, F5) — fixed in Phase 1. Houdini part = F3. ZBrush part = compiled binary, `legacy/` |
| [#62](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/62) | Maya 2022 not running script as it should | py3 breakage + F1. Not covered by current phases |
| [#59](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/59) | ZBrush 2021.7 can't export, import fine | Compiled binary tooling (F15). Out of scope — `legacy/` |
| [#57](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/57) | Cinema 4D R23/S24 not working | Same as #66. Out of scope — `legacy/` |
| [#56](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/56) | 3ds Max 2022 needs updates | MaxPlus removed in Max 2020; scripts dead. Out of scope — `legacy/` |
| [#3](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/3) | Morph/Blendshape support for Maya | Feature request; out of scope |

## 4. Consequences for the next phases

* **Phase 1 (Blender 4.2+):** fixes F4, F5, F12(read side), honors both UV
  forms and `None` encodings (F9), writes spec-canonical output
  (`VERTICES` first, discontinuous UVs, no `VERTEXNORMALS`), adds
  `OD_CPE_PATH`. Closes the Blender halves of #64.
* **Phase 2 (Rhino 8):** replaces the F10 stubs with RhinoCommon/CPython
  implementations per FORMAT.md (n-gon fan on paste, render mesh + warning on
  copy of Breps — cf. #67), adds `OD_CPE_PATH`.
* **Phase 3 (tests):** golden files must exercise the reader-conformance
  checklist of FORMAT.md §7 — mixed UV forms, `None` weights, `SUBD`/`CCSS`
  polytypes — not just the happy path.
* **Legacy move:** ZBrush, XSI, Lightwave, Modo, Substance, 3DCoat, Unity,
  C4D, Sketchup, Moi3D, 3DSMax move under `legacy/` unmodified. Maya and
  Houdini are in neither the modernization phases nor the legacy list; they
  currently stay in place untouched (F1, F2, F3 remain open upstream
  breakage) pending a maintainer decision.
