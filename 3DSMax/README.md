# OD Copy Paste External — 3ds Max 2021+

pymxs / Python 3 rewrite replacing the MaxPlus scripts (MaxPlus was removed
in Max 2020 — upstream #56). Exchange format:
[`docs/FORMAT.md`](../docs/FORMAT.md).

## Install / run

*Scripting ▸ Run Script…* on `3DSMax_CopyToExternal.py` /
`3DSMax_PasteFromExternal.py`, or wrap each in a macroscript for a toolbar
button:

```maxscript
macroScript OD_Copy category:"OD_CopyPasteExternal"
( python.ExecuteFile @"C:\path\to\3DSMax_CopyToExternal.py" )
```

## What copy does

Selected objects, world-space, modifiers baked (`snapshotAsMesh`), merged
into one triangle mesh: per-object material name as polygon surface, map
channel 1 as discontinuous UV samples. System units convert to the format's
meters (Max defaults to inches — check *Customize ▸ Units Setup*).

## What paste does

Rebuilds an `ODCopy` editable mesh: polygons fan-triangulated (Max TriMesh),
map channel 1 from the first UV map (discontinuous over continuous), one
material per surface name — a MultiMaterial with per-face IDs when there are
several. Weight/morph maps are reported in the listener and skipped.

## Conventions handled for you

Max is Z-up right-handed like Blender: coordinates map as `(x, z, -y)` /
`(x, -z, y)` (pure rotation, winding unchanged); MAXScript's 1-based
indices convert to the format's 0-based. `OD_CPE_PATH` relocates the
exchange file, as everywhere else.
