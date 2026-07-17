# OD Copy Paste External — Cinema 4D R23+/2024+

Native Python rewrite (upstream #57/#66): no OBJ export dialog, no compiled
converters. Exchange format: [`docs/FORMAT.md`](../docs/FORMAT.md).

## Install / run

*Extensions ▸ Script Manager*, load `C4D_CopyToExternal.py` and
`C4D_PasteFromExternal.py`, run them (or bind shortcuts via
*Customize Commands*).

## What copy does

Selected **polygon objects** (press `C` on parametric objects first),
world-space, merged into the one mesh the format allows: per-object material
name as polygon surface, UVW tag as discontinuous UV samples, **Vertex Map
tags as weight maps**. Document scale converts to the format's meters.

## What paste does

Rebuilds the exchange file as an `ODCopy` PolygonObject: tris/quads native,
n-gons fan-triangulated, UVW tag from the first UV map, weight maps as
Vertex Map tags, **one material per surface name** (with polygon-selection
restrictions when there are several). Morph maps are reported in the
console and skipped. Everything sits in one undo step.

## Conventions handled for you

Cinema 4D is left-handed Y-up; the format is right-handed: Z is negated and
polygon winding reversed, both ways. C4D's UV origin is top-left, the
format's bottom-left: V is flipped both ways. `OD_CPE_PATH` relocates the
exchange file, as everywhere else.
