# OD Copy Paste External — Maya 2022+

OpenMaya 2.0 / Python 3 rewrite of the Maya implementation. The exchange
format is specified in [`docs/FORMAT.md`](../docs/FORMAT.md).

## Install / run

Load each script in the Maya Script Editor (Python tab) and run it, or make
shelf buttons from them. Maya 2022+ (Python 3) only.

## What copy does (`maya_ExportToExternal.py`)

* Exports every **selected mesh**, merged into the single mesh the format
  allows.
* Per-face **surface-shader names** (e.g. `lambert1`) become polygon
  surfaces.
* Every **UV set** is exported as a UV map with true per-face-vertex
  (discontinuous) samples.
* **Skin weights**: if the mesh has a skinCluster, one `WEIGHT` section per
  influence (joint), in vertex order.
* **Blend shapes**: each target becomes a sparse `MORPH` section (deltas
  read from the blendShape node, `None` for untouched vertices).
* Maya's internal centimeters are converted to the format's meters (×0.01),
  regardless of the UI unit. Axes and winding are identical (Y-up
  right-handed, OBJ winding) — no rotation.

## What paste does (`maya_PasteFromExternal.py`)

* Builds the mesh natively — **n-gons included** (no fan triangulation
  needed in Maya).
* Every UV map becomes a **UV set** with true discontinuous assignment;
  faces whose corners lack UVs stay unassigned.
* Surface names become **lambert shaders** with shading groups (reused when
  a node of that name already exists); `Default`-only files go to
  `initialShadingGroup`.
* Morph maps become **blend-shape targets** on an `ODCopyMorphs` deformer.
* Weight maps are **listed and skipped** — skin weights only make sense
  against a joint hierarchy, which a paste cannot invent.
* Meters convert back to centimeters (×100). The historical 90° rotation of
  the old script (audit F16) is gone: Maya↔Maya round-trips are exact.

## Exchange file location

`ODVertexData.txt` in the system temp directory, or the directory named by
the **`OD_CPE_PATH`** environment variable (network share use case) —
consistent with the Blender and Rhino implementations.
