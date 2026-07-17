# OD Copy Paste External — SketchUp 2017+

Full Ruby rewrite of the upstream paste-only console snippet (which pasted
models upside down — axis conversion applied in the wrong direction — at
100× the wrong scale, and only handled quads). Copy **and** paste, proper
extension. Exchange format: [`docs/FORMAT.md`](../docs/FORMAT.md).

## Install

Copy `OD_CopyPasteExternal.rb` into the SketchUp *Plugins* folder
(*Window ▸ Preferences ▸ Extensions* shows the folder; or use Extension
Manager on a zipped `.rbz`). Two entries appear in the **Extensions** menu.

## What copy does

Selected **faces** (enter groups/components to select their faces),
deduplicated vertices in meters (SketchUp's internal inches converted),
per-face material name as surface, and — for textured materials — UVs via
`UVHelper` as discontinuous samples. Face outer loops preserve n-gons.

## What paste does

A new `ODCopy` group in one undo step: faces added natively (n-gons kept
when planar, fan-triangulated otherwise), SketchUp's automatic face
flipping corrected against the polygon's Newell normal, one material per
surface name, UVs applied with `position_material`. Weight/morph maps are
listed in the Ruby console and skipped. Degenerate faces are counted, not
fatal.

## Conventions handled for you

SketchUp is Z-up right-handed: `(x, z, -y)` on write, `(x, -z, y)` on read
(pure rotation, winding unchanged), inches ↔ meters. `OD_CPE_PATH`
relocates the exchange file, as everywhere else.
