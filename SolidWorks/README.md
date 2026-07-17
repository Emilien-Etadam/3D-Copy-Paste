# OD Copy Paste External — SolidWorks (Parasolid side-channel)

SolidWorks exchanges **exact B-rep geometry**, not meshes: this integration
uses the `ODSolidData.x_t` side-channel defined in
[`docs/FORMAT.md`](../docs/FORMAT.md) §7 — the same copy/paste semantics as
the mesh file, but carrying native Parasolid data. SolidWorks and Plasticity
both sit on the Parasolid kernel, so geometry passes through **exactly**, no
tessellation, no re-fitting.

## Install

For each of `OD_CopyToExternal.bas` and `OD_PasteFromExternal.bas`:

1. *Tools ▸ Macro ▸ New…*, name it, the VBA editor opens.
2. *File ▸ Import File…* and pick the `.bas` (or paste its contents over
   the default module).
3. Save. Bind the macro to a toolbar button or shortcut via
   *Tools ▸ Customize ▸ Commands ▸ Macro*.

The macros use late binding and literal constants — no type-library
references to set up. `OD_CPE_PATH` relocates the exchange directory, same
as everywhere else (falls back to `%TEMP%`).

## Usage

* **Copy** (`OD_CopyToExternal`): exports the active part or assembly to
  `ODSolidData.x_t` in the exchange directory.
* **Paste** (`OD_PasteFromExternal`): imports that file as a new document
  with the exact geometry.

### With Plasticity

* Plasticity → SolidWorks: in Plasticity, *File ▸ Export ▸ Parasolid
  (.x_t)* to the exchange path (e.g. `%TEMP%\ODSolidData.x_t`), then run the
  paste macro in SolidWorks.
* SolidWorks → Plasticity: run the copy macro, then in Plasticity
  *File ▸ Import* the same path.

### Meshes

For mesh workflows (into Blender, Maya, render tools…), copy from SolidWorks
is better served by the CAD→mesh applications themselves; SolidWorks has no
useful arbitrary-mesh paste. If you need it anyway, `tools/od_obj.py` plus
SolidWorks' OBJ/STL import gets meshes in as graphics bodies.
