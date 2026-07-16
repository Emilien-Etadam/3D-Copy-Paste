# The ODVertexData interchange format

This document is the normative specification of the intermediate file used by
OD_CopyPasteExternal to move mesh data between 3D applications. Until now the
format existed only implicitly in the per-application scripts; this spec was
reverse-engineered from the Modo kit (the original reference implementation),
Lightwave, Blender, Houdini, Maya, Rhino and the OBJ converter sources
(`docs/objToVertData.py`, `docs/vertDataToObj.py`) used by ZBrush, Substance
Painter, 3D-Coat and Moi3D.

**Backward compatibility is mandatory.** A file written by any historical
implementation (e.g. the Modo kit) must still paste correctly. Where
implementations disagree, this document describes both what writers SHOULD
emit and what readers MUST accept.

## 1. File name and location

* File name: **`ODVertexData.txt`** — exactly this, in every implementation.
  (Prose in the upstream README calls it "ODVertData.txt"; no code ever used
  that name.)
* Location: the system temporary directory, i.e. Python's
  `tempfile.gettempdir()`, resolved independently by each application. The
  design assumption is that all apps on one machine resolve the same
  directory.
  * Known deviation: the Houdini scripts use `gettempdir() + "/.."` because
    Houdini on Windows redirects its temp dir to a private
    `%TEMP%\houdini_temp` subfolder. On Linux/macOS this resolves *outside*
    the shared temp dir (see `docs/AUDIT.md`, finding F2).
* Modernized implementations (Blender, Rhino) additionally honor the
  **`OD_CPE_PATH`** environment variable: if set, it names the directory that
  contains `ODVertexData.txt` instead of `tempfile.gettempdir()` (network
  share / Dropbox use case). Legacy implementations do not read it.

## 2. Lexical structure

* Plain ASCII text. Writers emit `\n` line endings; readers MUST tolerate
  `\r\n` (all historical parsers `strip()` each payload token).
* One record per line. No comments, no blank-line significance (a single
  trailing newline at end of file is common).
* The file is a sequence of **sections**. Each section starts with a header
  line of the form `KEYWORD:arg[:arg...]` and is followed by a fixed number
  of payload lines determined by the header (or, for `WEIGHT`/`MORPH`, by the
  vertex count).
* Historical parsers do not parse sequentially: they scan **every** line of
  the file with `line.startswith(KEYWORD)` to locate section headers, then
  read payload lines by absolute offset from the header. Consequences:
  * Unknown sections are skipped gracefully — the format is forward
    extensible.
  * A payload line must never begin with a section keyword. In practice
    payload lines begin with a digit, `-`, `+`, `.` or `None`, so this holds.
  * `MORPH` and `WEIGHT` are matched *without* the trailing colon
    (`startswith("MORPH")`), so no future keyword may begin with these words.
* Numbers are written with Python `str(float)` / `str(int)` semantics and
  parsed with `float()` / `int()`. Readers MUST accept scientific notation
  (`1e-05`), which Python emits for small magnitudes.

## 3. Sections

### 3.1 `VERTICES:<count>` — required, first section

Followed by `<count>` lines, one per vertex:

```
<x> <y> <z>
```

Three space-separated floats. Vertex indices are implicit: the first payload
line is vertex `0`, the second vertex `1`, etc. **All indices in this format
are 0-based.**

Writers MUST emit exactly one `VERTICES` section and SHOULD make its header
the **first line of the file** (the Modo morph reader hard-codes that the
first vertex is on line 1 of the file; see AUDIT F8).

### 3.2 `POLYGONS:<count>` — required

Followed by `<count>` lines, one per polygon:

```
<i0>,<i1>,...,<iN>;;<surface>;;<polytype>
```

* Comma-separated list of 0-based vertex indices, in winding order (§4).
  Arbitrary polygon size: triangles, quads and n-gons are all legal.
* `<surface>` — material/surface name assigned to the polygon. `Default` when
  the source app has no material. The name MUST NOT contain `;;` or a
  newline; anything else (spaces, `:`) is legal here.
* `<polytype>` — one of:
  * `FACE` — plain polygon.
  * `SUBD` — legacy subdivision cage polygon (Lightwave *subpatch*,
    Modo *SubD*).
  * `CCSS` — Catmull-Clark subdivision cage polygon (Lightwave *CC*,
    Modo *Pixar SubD/PSUB*).

  Apps without a matching concept read everything as a plain face and write
  `FACE`.

### 3.3 `WEIGHT:<name>` — optional, repeatable (one section per weight map)

Followed by exactly *V* lines (V = vertex count), in vertex order:

```
<w>        a single float, or
None       vertex not present in the map
```

Readers MUST treat `None` as "no assignment" (skip the vertex), not as 0.0.
Lightwave writes `0.0` instead of `None`; Blender writes an explicit value
for every vertex. The map `<name>` MUST NOT contain `:` (parsers split the
header on `:`), `;;`, or a newline.

### 3.4 `MORPH:<name>` — optional, repeatable (one section per morph map)

Followed by exactly *V* lines, in vertex order:

```
<dx> <dy> <dz>    relative offset from the base position, or
None              vertex not affected by the morph
```

Morphs are **relative deltas** in file coordinate space (§4), not absolute
positions. Lightwave writes `0 0 0` instead of `None`. Blender maps morphs
to shape keys (delta = `key.co - basis.co` per vertex). Same name-character
constraints as `WEIGHT`.

### 3.5 `UV:<name>:<count>` — optional, repeatable (one section per UV map)

Followed by exactly `<count>` lines. `<count>` is the number of UV *samples*
(not vertices, not polygons). Two line forms exist and may be mixed within
one section:

```
<u> <v>:PLY:<polyIdx>:PNT:<vertIdx>     discontinuous (per-polygon-vertex) UV
<u> <v>:PNT:<vertIdx>                   continuous (per-vertex) UV
```

* Discontinuous form: the UV applies to vertex `<vertIdx>` *within* polygon
  `<polyIdx>` only (one "loop"/"face-vertex" in Blender/Houdini terms, a
  per-poly vmap value in LW/Modo terms).
* Continuous form: the UV applies to vertex `<vertIdx>` in every polygon that
  contains it, unless overridden by a discontinuous entry for a specific
  polygon. Only Lightwave writes this form (for vertices whose UV is shared
  across all their polygons); every other writer emits all samples in
  discontinuous form.
* Readers distinguish the forms by field count after splitting on `:`
  (5 fields = discontinuous, 3 fields = continuous). Readers MUST support
  both forms and MUST use the `PLY`/`PNT` indices — they MUST NOT assume the
  samples appear in polygon/loop order (Lightwave writes all discontinuous
  samples first, then all continuous ones; Houdini writes samples in reversed
  per-polygon vertex order).
* UV space is the standard OBJ convention: origin bottom-left, `v` up. No
  historical implementation flips `v`.
* A complete writer emits one sample for every polygon-vertex incidence
  (sum of polygon sizes) in discontinuous form; but readers MUST NOT rely on
  full coverage — samples may be sparse.

### 3.6 `VERTEXNORMALS` — optional, deprecated

Two mutually incompatible dialects exist in the wild:

```
VERTEXNORMALS:<count>                            Lightwave / OBJ converter
<x> <y> <z>                                      one line per polygon-vertex,
                                                 in polygon winding order

VERTEXNORMALS:VertexNormals:<count>              Modo
<x> <y> <z>:PLY:<polyIdx>:PNT:<vertIdx>          one line per polygon-vertex
```

Only Modo's paste consumes this section (and only its own dialect — it reads
the count from the *third* `:`-field and crashes on the Lightwave dialect).
All other readers ignore it. **Writers SHOULD NOT emit this section; readers
SHOULD skip it.** It is documented here only so parsers can step over both
dialects safely.

## 4. Coordinate system, units and winding

File space is the **OBJ convention**: right-handed, **+Y up**, +X right,
+Z toward the viewer. Units are meters (no unit metadata exists; Modo/LW
meters are the de-facto reference — Sketchup's paste applies its own ×100
scaling internally). Polygon winding is **counter-clockwise viewed from the
front/outside** (again as in OBJ). Vertex positions, morph deltas and vertex
normals are all expressed in this space.

The OBJ converters copy coordinates and index order 1:1 (only shifting the
index base), which is what anchors the file convention to OBJ's.

Per-application conversions observed in the historical implementations:

| Application | App space | App → file (write) | File → app (read) | Winding |
|---|---|---|---|---|
| Modo | Y-up RH | `(x, y, z)` | `(x, y, z)` | unchanged |
| Lightwave | Y-up LH | `(x, y, -z)` | `(x, y, -z)` | reversed both ways (mirror flips handedness) |
| Blender | Z-up RH | `(x, z, -y)` | `(x, -z, y)` | unchanged (pure rotation) |
| 3ds Max | Z-up RH | `(x, z, -y)` | `(x, -z, y)` | unchanged |
| Rhino | Z-up RH | `(x, z, -y)` | `(x, -z, y)` | unchanged |
| Houdini | Y-up RH | `(x, y, z)` | `(x, y, z)` | reversed both ways (Houdini front-face winding is opposite) |
| Maya | Y-up RH | `(x, y, z)` | `(x, y, z)` (a legacy 90° paste rotation was removed in this fork, see AUDIT F16) | unchanged |
| Sketchup (paste only) | Z-up RH | — | `(x, -z, y)` ×100 | unchanged |
| XSI | Y-up RH | `(x, y, z)` | `(x, y, z)` | unchanged |
| OBJ converters (ZBrush, Substance, 3D-Coat, Moi3D) | OBJ | identity | identity | unchanged |

Rule of thumb for new implementations: express the mesh as you would in a
Wavefront OBJ file, then use 0-based indices and the section syntax above.

## 5. Section ordering and cardinality

* Exactly one `VERTICES` and one `POLYGONS` section per file (one mesh per
  file). Several historical parsers nominally collect multiples, but behavior
  is inconsistent (see AUDIT F14) — writers MUST NOT emit more than one.
* Canonical writer order (Modo): `VERTICES`, `POLYGONS`, all `WEIGHT`
  sections, all `MORPH` sections, all `UV` sections, `VERTEXNORMALS`.
  Lightwave orders `WEIGHT`, `UV`, `MORPH` instead. Readers locate sections
  by header scan, so any order after `VERTICES`/`POLYGONS` MUST be accepted;
  writers SHOULD use the canonical order.
* Zero or more `WEIGHT`, `MORPH`, `UV` sections; at most one `VERTEXNORMALS`.

## 6. Annotated example — unit cube with one UV map

This is the upstream reference cube (`docs/datafile_example.txt`) reduced to
vertices, polygons and a single UV map. The `#` annotations are **not part of
the format** — a real file contains only the plain lines.

```
VERTICES:8                                    # section header: 8 vertices follow
-0.5 -0.5 -0.5                                # vertex 0  (x y z, file space: Y up, RH)
-0.5 -0.5 0.5                                 # vertex 1
-0.5 0.5 0.5                                  # vertex 2
-0.5 0.5 -0.5                                 # vertex 3
0.5 -0.5 -0.5                                 # vertex 4
0.5 -0.5 0.5                                  # vertex 5
0.5 0.5 0.5                                   # vertex 6
0.5 0.5 -0.5                                  # vertex 7
POLYGONS:6                                    # 6 polygons follow
0,1,2,3;;Default;;FACE                        # polygon 0: quad over verts 0,1,2,3 (CCW from
                                              #   outside), material "Default", plain face
0,4,5,1;;Default;;FACE                        # polygon 1
1,5,6,2;;Default;;FACE                        # polygon 2
3,2,6,7;;Default;;FACE                        # polygon 3
0,3,7,4;;Default;;FACE                        # polygon 4
4,7,6,5;;Default;;FACE                        # polygon 5
UV:txuvmap:24                                 # UV map named "txuvmap", 24 samples
0.339743584394 0.339743584394:PLY:0:PNT:0     # discontinuous: u v for vertex 0 inside polygon 0
0.660256385803 0.339743584394:PLY:0:PNT:1     # vertex 1 inside polygon 0
0.660256385803 0.660256385803:PLY:0:PNT:2
0.339743584394 0.660256385803:PLY:0:PNT:3
0.660256385803 0.326923072338:PLY:1:PNT:5
0.339743584394 0.326923072338:PLY:1:PNT:1
0.00641027092934 0.339743584394:PLY:3:PNT:3
0.00641027092934 0.660256385803:PLY:3:PNT:2
0.326923072338 0.660256385803:PLY:3:PNT:6
0.326923072338 0.339743584394:PLY:3:PNT:7
0.673076927662 0.00641025649384:PLY:4:PNT:0
0.993589758873 0.00641025649384:PLY:4:PNT:4
0.673076927662 0.339743584394:PLY:5:PNT:4
0.673076927662 0.660256385803:PLY:5:PNT:7
0.993589758873 0.660256385803:PLY:5:PNT:6
0.993589758873 0.339743584394:PLY:5:PNT:5
0.339743584394 0.00641025649384:PNT:0         # continuous: u v for vertex 0 in every polygon
0.660256385803 0.00641025649384:PNT:4         #   not covered by a discontinuous entry above
0.00641027092934 0.00641025649384:PNT:1
0.326923072338 0.00641025649384:PNT:5
0.326923072338 0.326923072338:PNT:6
0.00641027092934 0.326923072338:PNT:2
0.673076927662 0.326923072338:PNT:3
0.993589758873 0.326923072338:PNT:7
```

Note how the 24 samples cover the 24 polygon-vertex incidences (6 quads × 4)
as a mix of 16 discontinuous and 8 continuous entries — a Lightwave-style
writer output. A Modo/Blender-style writer would emit the same information as
24 discontinuous entries in polygon order.

For a fuller example including `WEIGHT` and `MORPH` sections, see
`docs/datafile_example.txt` (the upstream original, unmodified).

## 7. Reader conformance checklist

A modern reader MUST:

1. Locate sections by scanning line prefixes; ignore unknown sections.
2. Accept 0-based indices everywhere; accept n-gons.
3. Accept `None` in `WEIGHT`/`MORPH` payloads (and `0.0` / `0 0 0`
   equivalents).
4. Accept both UV line forms, honoring `PLY`/`PNT` indices rather than sample
   order.
5. Accept both `VERTEXNORMALS` dialects at least well enough to skip them.
6. Accept `FACE`, `SUBD` and `CCSS` polytypes (degrading `SUBD`/`CCSS` to a
   plain face plus, where available, a subdivision modifier/flag).
7. Apply the coordinate conversion of §4 for its host application.

A modern writer MUST: write `VERTICES` as the first line; use `\n` endings;
one mesh per file; discontinuous UV form; no `VERTEXNORMALS`; `None` for
unassigned weight/morph vertices; material `Default` when unknown.
