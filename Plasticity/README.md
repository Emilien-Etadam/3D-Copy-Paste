# OD Copy Paste External — Plasticity

Two complementary routes, both conforming to
[`docs/FORMAT.md`](../docs/FORMAT.md).

## 1. Live copy via the bridge (`plasticity_copy.py`)

Plasticity ships a WebSocket bridge server (the one its official Blender
addon uses). `plasticity_copy.py` speaks the same protocol — plain Python 3,
no dependencies:

```
python3 Plasticity/plasticity_copy.py            # copy visible solids/sheets
python3 Plasticity/plasticity_copy.py --watch    # re-copy on every change
python3 Plasticity/plasticity_copy.py --all      # include hidden objects
```

1. In Plasticity, enable the bridge server (the plug icon / *Run in server
   mode*; default `localhost:8980`, override with `--server`).
2. Run the script: every visible solid and sheet is written to the exchange
   file (merged, one surface name per Plasticity object), ready to paste in
   Blender, Rhino, Maya, Houdini…
3. `--watch` keeps the connection open and rewrites the file after each
   modeling change — combined with a paste in the target application you get
   a near-live link.

Plasticity facets are triangles in right-handed Y-up space — exactly the
exchange format's conventions, so geometry passes through unchanged
(`--scale` is available if your pipeline needs a unit factor).

The bridge is **one-way** (Plasticity → others): the protocol has no
paste-into-Plasticity channel suitable for arbitrary meshes.

## 2. Round-trip via OBJ (`tools/od_obj.py`)

* **Copy from Plasticity**: File ▸ Export ▸ OBJ, then
  `python3 tools/od_obj.py --from-obj export.obj`.
* **Paste into Plasticity**: `python3 tools/od_obj.py --to-obj`, then
  File ▸ Import the resulting `OD_CPE.obj`.

## Exchanging exact CAD geometry with SolidWorks

Meshes lose the B-rep. For Plasticity ↔ SolidWorks, use the **Parasolid
side-channel**: export `.x_t` from Plasticity to the `ODSolidData.x_t`
convention path — see [`SolidWorks/`](../SolidWorks/) (roadmap phase 8).

## Protocol credit

The bridge protocol implementation follows the official MIT-licensed
[plasticity-blender-addon](https://github.com/nkallen/plasticity-blender-addon)
by Nick Kallen.
