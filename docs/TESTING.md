# Testing

## Golden files (`tests/golden/`)

Reference ODVertexData files conforming to [FORMAT.md](FORMAT.md):

| File | Contents | What it exercises |
|---|---|---|
| `cube_uv.txt` | Unit cube, 6 quads, one UV map with **16 discontinuous + 8 continuous samples** (the upstream reference cube) | Mixed UV sample forms, `PLY`/`PNT` index handling (audit F4) |
| `weighted_plane.txt` | 2×2-quad plane, material `Checker`, two weight maps (with `None` entries), one morph map (`None` + delta), one all-continuous UV map | Weight `None` semantics, morph deltas/shape keys, material creation, continuous-only UVs |

Any new golden file dropped into `tests/golden/` is picked up automatically
by the Blender round-trip test.

## Blender — automated round-trip

```
blender --background --python tests/test_blender_roundtrip.py
```

or, without a Blender install (standalone bpy module, Python 3.11):

```
pip install "bpy==4.2.*"
python3 tests/test_blender_roundtrip.py
```

For each golden file the test pastes it with the extension's paste operator,
copies the resulting mesh back, and compares the two files **semantically**
within a `1e-5` float tolerance: identical vertices/polygons/surfaces,
weights (`None` ≡ unassigned), morph deltas (`None` ≡ zero delta), and UV
maps resolved to the same per-polygon-corner mapping regardless of
continuous/discontinuous encoding. Exit code 0 = pass; failures list the
differences.

Status: passes 2/2 against Blender 4.2.22 LTS (bpy module).

## Blender — manual checks (once per release)

1. Install the extension: zip `Blender/od_copy_paste_external/` and use
   *Preferences ▸ Get Extensions ▸ Install from Disk…*; both commands appear
   in the 3D Viewport *Object* menu.
2. Copy the default cube; check `ODVertexData.txt` appears in the system
   temp dir and starts with `VERTICES:8`.
3. Paste `tests/golden/weighted_plane.txt` (copy it over the temp file):
   expect a 2×2 plane with a `Checker` material, two vertex groups with the
   center/right vertices unassigned, shape key `bump` raising the center
   vertex, and a `planar` UV map.
4. Set `OD_CPE_PATH` to another directory, restart Blender, and confirm both
   operators use it (path is shown in the info report).

## Rhino 8 — manual checklist

Run both scripts from the `ScriptEditor` command (they are CPython-only,
`#! python 3`). Watch the command-line console: every action and skip is
reported with an `OD_CopyPasteExternal:` prefix.

### Copy

1. **Mesh box**: `_Box` then `_Mesh` it, select the mesh, run
   `Rhino_CopyToExternal.py`. Expect `copied 8 vertices / … to …` in the
   console and a `VERTICES:8` file at the reported path.
2. **Brep without render mesh**: in a fresh wireframe file, select an
   unmeshed `_Box` (Brep) and copy. Expect *skipped … no render mesh
   available* — nothing silently meshed.
3. **Brep with render mesh**: shade the viewport once, copy again. Expect
   *using its render mesh (N faces)* warning and a valid file.
4. **Multiple objects with materials**: assign two different render
   materials, select both objects, copy. The file's `POLYGONS` lines must
   carry each object's material name as surface.
5. **Units**: in a millimeters document, copy a 1000 mm box; the file must
   contain coordinates around `0.5` (meters), not `500`.

### Paste

6. **Golden cube**: copy `tests/golden/cube_uv.txt` over the exchange file,
   run `Rhino_PasteFromExternal.py` in a meters document. Expect a selected
   1 m mesh box named `ODCopy`; with a textured material, the UVs match the
   cube's unwrap. A console note about collapsed UV seams is expected
   (Rhino stores one UV per vertex).
7. **Weighted plane**: paste `tests/golden/weighted_plane.txt`. Expect the
   plane plus a console line *ignored 3 weight/morph maps* naming
   `edge_falloff`, `left_side`, `bump`.
8. **N-gon**: paste a file containing a polygon with 5+ indices (e.g. from
   Blender: an untriangulated n-gon). Expect a single Rhino ngon face, not
   visible fan triangles (`_ExtractMeshFaces` shows the fan underneath).
9. **Units**: paste the golden cube into a millimeters document; the box
   must be 1000 mm.
10. **Legacy compatibility**: copy an object from any legacy implementation
    (e.g. the Modo kit or an old ODVertexData.txt you have around) and paste
    it in Rhino — geometry must arrive intact (weights/morphs reported and
    skipped).

### Shared

11. **`OD_CPE_PATH`**: set the variable to a writable directory, restart
    Rhino, copy in Rhino and paste in Blender (started with the same
    variable) — the file must appear in that directory, and the transfer
    must work across both applications.

## Maya 2022+ — manual checklist

Run the scripts from the Script Editor (Python 3). Console messages are
prefixed `OD_CopyPasteExternal:`.

1. **Copy a cube**: `polyCube -w 100 -h 100 -d 100` (cm), select, run the
   export. The file must contain coordinates around `0.5` (meters) and
   `VERTICES:8`.
2. **UV sets**: copy a mesh with two UV sets; both must appear as `UV:`
   sections with per-face-corner samples.
3. **Skin weights**: copy a skinned mesh; one `WEIGHT` section per joint.
4. **Blend shapes**: copy a mesh with blendShape targets; sparse `MORPH`
   sections (`None` on untouched vertices).
5. **Paste golden cube** (`tests/golden/cube_uv.txt`): 1 m cube (100 cm),
   UVs correct in the UV Editor, no rotation (top face up — F16).
6. **Paste weighted plane**: plane with a `Checker` lambert, an
   `ODCopyMorphs` blendShape with a `bump` target raising the center
   vertex, and a console note listing the two skipped weight maps.
7. **N-gon paste**: a file with a 6-index polygon must produce a single
   Maya n-gon face.
8. **Maya↔Maya round-trip**: copy any mesh, paste it — geometry, UVs and
   orientation must match the original exactly.
9. **`OD_CPE_PATH`**: set it, restart Maya, verify both scripts use it.

## Plasticity — manual checklist

1. Enable the bridge in Plasticity, model a box, run
   `python3 Plasticity/plasticity_copy.py`: console reports 1 object, and
   pasting in Blender/Rhino gives the box at the right size and orientation.
2. `--watch`: edit the box in Plasticity; the exchange file timestamp must
   change within a second and re-pasting shows the edit.
3. Hidden objects are excluded by default; `--all` includes them.
4. OBJ round-trip: export OBJ from Plasticity, `tools/od_obj.py --from-obj`,
   paste elsewhere; then the reverse with `--to-obj` + File ▸ Import.

## SolidWorks — manual checklist (Parasolid side-channel)

1. Install both macros per `SolidWorks/README.md` (VBA import, no
   references to configure).
2. **Copy**: open a part with a few bodies, run `OD_CopyToExternal`;
   expect a confirmation dialog and `ODSolidData.x_t` in `%TEMP%` (or
   `OD_CPE_PATH`).
3. **Paste**: run `OD_PasteFromExternal` in a fresh session; the geometry
   opens as an imported document, exact (check a dimension).
4. **Plasticity round-trip**: export a Plasticity model as `.x_t` to the
   exchange path, paste in SolidWorks; then copy from SolidWorks and
   File ▸ Import in Plasticity. Faces must remain analytic (no tessellation).
5. **No file**: run the paste macro with no `ODSolidData.x_t` present —
   expect the explanatory dialog, no error.
6. The mesh channel is untouched: `ODVertexData.txt` copy/paste keeps
   working independently.

## Godot — manual checklist

Automated coverage: the CI job *Godot headless round-trip* runs
`Godot/tests/roundtrip_test.gd` against the golden files. Manual pass:

1. Enable the plugin (*Project ▸ Project Settings ▸ Plugins*); both entries
   appear under *Project ▸ Tools*.
2. Paste the golden cube in a 3D scene: an `ODCopy` MeshInstance3D appears,
   selected, right way up, with a `Default`-named material and correct UVs
   (assign a checker texture to verify).
3. **Winding**: faces must be visible from outside (Godot culls clockwise
   back faces — an inverted mesh looks inside-out).
4. Copy a Godot mesh (e.g. a `BoxMesh` converted to `ArrayMesh`) and paste
   it in Blender: orientation, UVs and material name must survive.
5. Paste the weighted plane: the output log lists the skipped
   weight/morph maps.

## Cinema 4D — manual checklist

1. Load both scripts in the Script Manager; run copy with nothing selected:
   explanatory dialog (mentions pressing `C` for parametric objects).
2. Copy an editable cube with a material and a Vertex Map tag: the file has
   `VERTICES:8`, the material name as surface, a `WEIGHT` section, and
   coordinates in meters (200 cm cube → `1.0` extents).
3. Paste the golden cube: an `ODCopy` object appears, right way round
   (winding/Z-mirror round-trip), with a `Default` material and correct UVs
   (checker texture in UVW projection).
4. Paste the weighted plane: `Checker` material, Vertex Map tag visible in
   weight-paint display, morph skip message in the console.
5. C4D↔Blender round-trip: orientation, UVs and material names must
   survive both directions.

## 3ds Max — manual checklist

1. Run the copy script with nothing selected: explanatory message box.
2. Copy a teapot with a named material in an **inches** document: the file
   has coordinates in meters (×0.0254), the material name as surface,
   discontinuous UV samples, and triangles only.
3. Paste the golden cube in a **millimeters** document: `ODCopy` appears at
   1000 mm, right way up, `Default` material, UVs correct on map channel 1.
4. Paste the weighted plane: `Checker` material, listener message listing
   the skipped weight/morph maps.
5. Max↔Blender round-trip: orientation, UVs and material names must
   survive both directions (upstream demo video workflow).

## Cross-application spot checks

With any two of {Blender, Rhino, a legacy app}: copy a cube with a UV map in
one, paste in the other, and verify scale (1 m cube), orientation (Y-up apps
and Z-up apps agree), winding (no inverted normals), and UVs. The format
conventions being exercised are documented in FORMAT.md §4.
