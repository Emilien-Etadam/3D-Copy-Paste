# OD Copy Paste External — Blender extension

Blender 4.2+ LTS implementation of the ODVertexData exchange
([format spec](../docs/FORMAT.md)). Supports vertices, polygons (n-gons
included), materials, UV maps (continuous and discontinuous samples), weight
maps (vertex groups) and morphs (shape keys). `SUBD`/`CCSS` polygons from
Modo/Lightwave paste as faces with a Subdivision Surface modifier.

Scripts for Blender 2.7x–3.x live in [`legacy/Blender/`](../legacy/Blender/)
and are unmaintained.

## Install

1. Zip the `od_copy_paste_external` folder (the zip must contain
   `blender_manifest.toml` at its top level inside the folder):
   `cd Blender && zip -r od_copy_paste_external.zip od_copy_paste_external`
2. In Blender: *Edit ▸ Preferences ▸ Get Extensions ▸ ⌄ (top-right menu) ▸
   Install from Disk…* and pick the zip.

Both commands appear in the 3D Viewport *Object* menu:

* **OD Copy To External** — writes the active mesh to the exchange file.
* **OD Paste From External** — rebuilds the mesh from the exchange file into
  the active mesh object (preserving its transform), or a new `ODCopy`
  object when none is active.

## Exchange file location

By default the file is `ODVertexData.txt` in the system temp directory —
the same location every other implementation uses, so cross-application
copy/paste works with no configuration.

Set the **`OD_CPE_PATH`** environment variable to a directory to relocate
the file (e.g. a network share or synced folder to exchange geometry across
machines). Blender must be started with the variable in its environment.
