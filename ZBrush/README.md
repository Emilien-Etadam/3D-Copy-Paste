# OD Copy Paste External — ZBrush 2021+

Rework of the ZBrush plugin (upstream #59, #34): the compiled
`objToVertData.exe` / `vertDataToObj.exe` converters — Windows-only,
antivirus-flagged, unbuildable — are replaced by a **cross-platform
Python 3 converter** (`ODCopyPaste/od_zbrush_convert.py`) called through
small `od_export`/`od_import` wrappers. **Python 3 must be on PATH**
(python.org, Microsoft Store, or Homebrew builds all work).

## Install

1. Copy the `ODCopyPaste/` folder **and** `ZBRUSH_ODCopyPasteExternal.txt`
   into `ZStartup/ZPlugs64/` (delete any old `.zsc` from a previous
   install).
2. In ZBrush: *Zscript ▸ Load ZScript* on the `.txt` once — ZBrush compiles
   it locally. Two buttons appear in the **Zplugin** palette:
   `TOOL: CopyToExt` and `TOOL: PasteFromExt`.

The stock Pixologic `ZFileUtils` helper libraries are kept (they only
launch the wrappers); the flagged converter binaries are gone.

## How it works

* **Copy**: ZBrush exports the current tool as OBJ, the wrapper converts it
  to the exchange file (verts, polys incl. n-gons, `usemtl` as surface,
  UVs as discontinuous samples).
* **Paste**: the wrapper converts the exchange file to OBJ (weight/morph
  sections dropped — no OBJ equivalent), ZBrush imports it.

`OD_CPE_PATH` relocates the exchange file, as everywhere else — set it
system-wide so the launched wrapper inherits it.
