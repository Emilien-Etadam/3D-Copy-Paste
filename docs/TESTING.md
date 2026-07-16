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

## Cross-application spot checks

With any two of {Blender, Rhino, a legacy app}: copy a cube with a UV map in
one, paste in the other, and verify scale (1 m cube), orientation (Y-up apps
and Z-up apps agree), winding (no inverted normals), and UVs. The format
conventions being exercised are documented in FORMAT.md §4.
