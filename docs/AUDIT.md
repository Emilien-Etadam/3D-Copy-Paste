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
| Houdini | yes | yes | verts, polys, weights (float point attrs), UVs | shelf tool creating embedded Python SOP | py3 paste (F3) and temp path (F2) fixed in this fork |
| Maya | yes | yes | verts, polys, "weights" via vertex color red channel | maya.cmds + OpenMaya | Header corruption (F1) and py2 syntax fixed in this fork; axis asymmetry remains (F16) |
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
  sees an empty file (including Maya's own, which reads the vertex count from
  line 0). Only unsaved scenes produce valid files. (Related upstream: #62,
  #70.) **Fixed in this fork**: the scene-name write was removed; the Maya
  paste's remaining Python 2 syntax (`except IndexError, e`) was also ported.
* **F2 — Houdini uses a different file path.** Both Houdini scripts use
  `tempfile.gettempdir() + os.sep + ".." + os.sep + "ODVertexData.txt"`. This
  compensates for Houdini's private `%TEMP%\houdini_temp` on Windows, but on
  Linux/macOS it resolves to the *parent* of the shared temp dir (e.g. `/`),
  so Houdini and every other app read/write different files. **Fixed in this
  fork**: both scripts now step up one level only when `gettempdir()` ends in
  a `houdini*` directory (same approach upstream PR #22 used for XSI's
  `xsi_temp`).
* **F3 — Houdini paste is still Python 2.** Upstream `858c4c7` converted only
  the copy script; `Houdini_PasteFromExternal.py` still uses `xrange` inside
  the embedded SOP code and fails on Houdini 18.5+ default py3 builds. This is
  the actual cause of open issues #64 (Houdini part) and #65. **Fixed in this
  fork**: the embedded paste script is ported to Python 3.
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
* **F16 — Maya copy and paste disagree on axes.** The copy writes Maya
  coordinates to the file unchanged (Maya is Y-up RH, matching file space),
  but the paste rotates the built mesh 90° about X and freezes the transform
  — i.e. it reads the file as `(x, −z, y)`, as if the target were Z-up.
  A Maya→Maya round-trip therefore comes back rotated, and pastes from any
  spec-conformant writer land on their side. Possibly intentional for
  Z-up-configured Maya installs; left as-is (documented in FORMAT.md §4)
  pending a maintainer decision.

## 3. Upstream open issues (as of 2026-07-15)

| # | Title | Relevance to this fork |
|---|---|---|
| [#71](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/71) | od_C/P needs update for Modo 17 | Modo kit is py2; Modo 16.1+ ship py3. Out of scope — Modo moves to `legacy/` unmodified |
| [#70](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/70) | Maya 2024/2025 support? | py2 syntax + F1, both fixed in this fork (F16 remains) |
| [#69](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/69) | Copying Curves data | Feature request; format has no curve section. Out of scope |
| [#68](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/68) | Any interest in Godot Engine? | Feature request; out of scope |
| [#67](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/67) | Meshing options | Feature request (NURBS meshing control). Phase 2's Rhino copy touches this: render mesh is used with an explicit warning |
| [#66](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/66) | Doesn't work with C4D | C4D OBJ-dialog wrapper broken on modern C4D. Out of scope — `legacy/` |
| [#65](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/65) | PasteFromExternal doesn't work in Houdini 19 | Root cause F3 (paste still py2); upstream fix only converted the copy script. Fixed in this fork |
| [#64](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/64) | Not working: Blender 3.0, Houdini 19, ZBrush 2022 | Blender copy crash (no shape keys) fixed upstream in `858c4c7`; Blender paste issues remain (F4, F5) — fixed in Phase 1. Houdini part = F3, fixed in this fork. ZBrush part = compiled binary, `legacy/` |
| [#62](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/62) | Maya 2022 not running script as it should | py3 breakage + F1, both fixed in this fork |
| [#59](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/59) | ZBrush 2021.7 can't export, import fine | Compiled binary tooling (F15). Out of scope — `legacy/` |
| [#57](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/57) | Cinema 4D R23/S24 not working | Same as #66. Out of scope — `legacy/` |
| [#56](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/56) | 3ds Max 2022 needs updates | MaxPlus removed in Max 2020; scripts dead. Out of scope — `legacy/` |
| [#3](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/3) | Morph/Blendshape support for Maya | Feature request; out of scope |

## 4. Upstream pull requests (complete history)

Upstream has **no open PRs**; 10 closed. Merged ones are already in this
fork's baseline. Relevant for format archaeology:

| PR | Title | State | Format relevance |
|---|---|---|---|
| [#73](https://github.com/heimlich1024/OD_CopyPasteExternal/pull/73) | LW_CopyPasteExternal.py updated for LW 2025.0.x | closed unmerged (Dec 2025, by its author) | API-level SWIG fixes for LW 2025; the only post-abandonment contribution. Worth revisiting if Lightwave ever leaves `legacy/` |
| [#58](https://github.com/heimlich1024/OD_CopyPasteExternal/pull/58) | copy morph shapes from object instead of all objects | merged | Blender copy: morphs read from the active object only |
| [#44](https://github.com/heimlich1024/OD_CopyPasteExternal/pull/44) | changes to run on blender version 2.80 | merged | Origin of the `Blender280/` variant |
| [#43](https://github.com/heimlich1024/OD_CopyPasteExternal/pull/43) | Fixed Vertex Normal Support In Modo | merged | **Origin of the Modo `VERTEXNORMALS` dialect** (F6) and of the post-paste normal-map selection bug (F7) |
| [#36](https://github.com/heimlich1024/OD_CopyPasteExternal/pull/36) | Add paste support for UVs, materials, preferences, and undo | merged | Unity paste features |
| [#35](https://github.com/heimlich1024/OD_CopyPasteExternal/pull/35) | Unity support | merged | Unity initial implementation |
| [#26](https://github.com/heimlich1024/OD_CopyPasteExternal/pull/26) | Lw pntvpmap | merged | Lightwave discontinuous-UV write path (`pntVPMap`) |
| [#24](https://github.com/heimlich1024/OD_CopyPasteExternal/pull/24) | Morphs for Pre-Lightwave 2015 did not have negative z values | merged | Confirms the LW morph-delta Z negation of FORMAT.md §4 — pre-2015 scripts lacked it and produced mirrored morphs |
| [#22](https://github.com/heimlich1024/OD_CopyPasteExternal/pull/22) | Temp path fix | merged | XSI strips `xsi_temp` segments from `gettempdir()` — same redirected-temp-dir problem Houdini works around with `gettempdir()/..` (F2). Precedent for making the path explicitly configurable (`OD_CPE_PATH`) |
| [#14](https://github.com/heimlich1024/OD_CopyPasteExternal/pull/14) | Initial XSI support | merged | XSI initial implementation |

## 5. Notable closed upstream issues

36 issues are closed upstream (full sweep done 2026-07-15; remaining gaps in
the issue numbering are PRs or deleted/spam entries). Most are
version-breakage reports superseded by the open ones in §3. The ones that
carry format information:

* [#4](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/4) /
  [#5](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/5) /
  [#6](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/6)
  (May 2017) — introduction of **discontinuous UV support** in Houdini,
  Blender and Modo; the historical reason the `UV` section has two line
  forms (FORMAT.md §3.5).
* [#54](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/54) — a
  Wings3D plugin developer asked how the mixed continuous/discontinuous UV
  listing in `docs/datafile_example.txt` should be interpreted; closed
  without a recorded answer. Exactly the ambiguity FORMAT.md §3.5 now
  resolves (the sample is Lightwave-style output; readers must honor
  `PLY`/`PNT` indices).
* [#60](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/60) —
  earlier duplicate of #65 (Houdini 19 paste, F3), closed without fix.
* [#8](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/8) —
  Maya→Modo copy error (2017), consistent with the F1 header corruption.
* [#34](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/34) —
  antivirus flagged the checked-in PyInstaller `.exe` converters as a
  trojan; supports F15's concern about unbuildable binaries in the repo.
* [#12](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/12) /
  [#37](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/37) —
  multiple-object copy/paste requested and never implemented; the format
  remains one-mesh-per-file (F14, FORMAT.md §5).
* [#1](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/1) —
  Blender paste duplicated vmaps on repeated paste; the reason the Blender
  paste clears vertex groups/shape keys/UV layers before applying new ones
  (behavior Phase 1 must preserve).

## 6. Consequences for the next phases

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
  C4D, Sketchup, Moi3D, 3DSMax move under `legacy/` unmodified. **Maya and
  Houdini stay at the top level** (maintainer decision, 2026-07-15) and
  received targeted fixes in this fork for F1, F2 and F3; the Maya axis
  asymmetry (F16) is documented but deliberately left unchanged.
