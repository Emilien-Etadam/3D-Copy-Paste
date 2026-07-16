# OD Copy Paste External — Rhino 8

CPython rewrite of the Rhino implementation for the Rhino 8 ScriptEditor
(RhinoCommon, `Rhino.Geometry.Mesh`), replacing the unfinished
rhinoscriptsyntax stubs (audit finding F10). The exchange format is specified
in [`docs/FORMAT.md`](../docs/FORMAT.md).

## Install / run

1. In Rhino 8, run the `ScriptEditor` command.
2. Open `Rhino_CopyToExternal.py` and `Rhino_PasteFromExternal.py` and run
   them from the editor — or create toolbar buttons/aliases running
   `-ScriptEditor <path-to-script>`.

The `#! python 3` shebang routes both scripts to CPython; they do not run in
Rhino 7's IronPython.

## What copy does

* Copies the **selected objects** (prompts if nothing is selected).
* Mesh objects are exported as-is.
* Breps, extrusions and SubDs are exported through their **existing render
  mesh**, with a console warning — nothing is meshed silently. If an object
  has no render mesh yet (never displayed shaded), it is skipped with an
  explanation; shade the viewport once or run `Mesh` first.
* Multiple objects are merged into the single mesh the format allows, each
  keeping its render material name as the polygon surface name.
* Texture coordinates are exported when present.
* Coordinates are converted from the document's model units to the format's
  meters, and from Rhino's Z-up to the format's Y-up.

## What paste does

* Builds a mesh from the exchange file: triangles and quads become native
  faces; **n-gons are fan-triangulated and regrouped as Rhino ngons**.
* Texture coordinates are applied when the file has a UV map. Rhino stores
  one UV per vertex, so discontinuous UV seams are collapsed (a console note
  reports how many samples were affected). Only the first UV map is applied.
* Weight and morph maps have no Rhino equivalent; they are listed in the
  console and skipped.
* `SUBD`/`CCSS` cage polygons paste as plain faces (console hint suggests
  `SubDFromMesh`).
* Meters are converted to the document's model units.

## Exchange file location

`ODVertexData.txt` in the system temp directory by default — the same
location every other implementation uses. Set the **`OD_CPE_PATH`**
environment variable to a directory (network share, synced folder) to
relocate it; Rhino must be started with the variable in its environment.
