# OD Copy Paste External — Moi3D

Pure-JScript rewrite: the compiled `objToVertData.exe` / `vertDataToObj.exe`
converters and the `.htm` dialog are gone — the OBJ↔ODVertexData conversion
now happens **inside the Moi scripts**, so the integration works on any
platform Moi runs on. Exchange format: [`docs/FORMAT.md`](../docs/FORMAT.md).

## Install

Copy `ODCopyToExternal.js` and `ODPasteFromExternal.js` into Moi's
**commands** folder. Run them via a shortcut key (Options ▸ Shortcut keys,
command name = file name) or the custom UI.

## How it works

* **Copy**: Moi exports the selection natively as an n-gon OBJ (no dialog,
  `NoUI=true`), and the script converts the OBJ text to the exchange file.
* **Paste**: the script converts the exchange file to OBJ text
  (weight/morph sections dropped — no OBJ equivalent) and Moi imports it
  natively. Meshes arrive as polygon data.

Moi and the format share the OBJ conventions (right-handed Y-up, CCW),
so geometry passes through unchanged.

## Exchange file location

The scripts use Moi's temp folder when the API exposes one, otherwise the
commands folder — **check the path shown in the confirmation popup**. To
share with other applications (or if the fallback landed in the commands
folder), set the `OD_CPE_PATH` variable at the top of *both* scripts to the
same absolute folder the other applications use (the system temp directory,
or your shared network folder).

## Tests

The conversion functions are `moi`-independent and unit-tested with Node
(`node tests/test_moi3d_logic.js`, in CI). In-Moi behavior: manual
checklist in [`docs/TESTING.md`](../docs/TESTING.md).
