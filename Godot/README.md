# OD Copy Paste External — Godot 4.4+

Editor addon answering upstream request
[#68](https://github.com/heimlich1024/OD_CopyPasteExternal/issues/68).
Exchange format: [`docs/FORMAT.md`](../docs/FORMAT.md).

## Install

Copy `addons/od_copy_paste_external/` into your project's `addons/` folder
and enable **OD Copy Paste External** in *Project ▸ Project Settings ▸
Plugins*. Two entries appear under *Project ▸ Tools*:

* **OD Copy To External** — writes the selected `MeshInstance3D` (all
  surfaces, with material/surface names and UVs) to the exchange file.
* **OD Paste From External** — rebuilds the exchange file's mesh as a new
  `ODCopy` node in the edited scene: one Godot surface per surface name
  (with a named `StandardMaterial3D`), n-gons fan-triangulated, UVs applied
  per corner, normals generated.

## Conventions handled for you

Godot and the format are both right-handed Y-up, so coordinates pass
through unchanged; polygon winding is reversed both ways (Godot's front
faces are clockwise, the format's counter-clockwise) and V is flipped both
ways (Godot's UV origin is top-left, the format's bottom-left).

Weight and morph maps have no direct equivalent on a plain `MeshInstance3D`
and are reported in the output log, then skipped.

`OD_CPE_PATH` relocates the exchange file, as everywhere else.

## Headless test

```
godot --headless --path Godot --script res://tests/roundtrip_test.gd
```

Runs in CI on every pull request (golden files → build → extract →
geometric comparison).
