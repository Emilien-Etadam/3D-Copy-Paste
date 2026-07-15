# Legacy implementations

Everything in this directory is **unmaintained upstream code**, kept verbatim
from the abandoned original project
([heimlich1024/OD_CopyPasteExternal](https://github.com/heimlich1024/OD_CopyPasteExternal))
for reference and for users whose pipelines still depend on it. None of it is
tested, fixed, or supported by this fork; several implementations are known to
be broken on current application versions (see
[`docs/AUDIT.md`](../docs/AUDIT.md) for details and upstream issue numbers).

| Directory | Notes |
|---|---|
| `3DCoat/` | Uses compiled Windows `.exe` converters |
| `3DSMax/` | MaxPlus API, removed in 3ds Max 2020+ (upstream #56) |
| `Blender/` | Pre-4.x scripts (2.7x/2.8x/2.9x/3.1x), superseded by the extension in [`../Blender/`](../Blender/) |
| `C4D/` | OBJ-dialog wrapper, broken on R23+ (upstream #57, #66) |
| `Lightwave/` | Python 2 (LW 2015–2019); see upstream PR #73 for an unmerged LW 2025 port |
| `Modo/` | Python 2 kit, broken on Modo 16.1+ (upstream #71). Historical reference implementation of the format |
| `Moi3D/` | Uses compiled Windows `.exe` converters |
| `Sketchup/` | Paste-only starting point |
| `SubstancePainter/` | Paste-only, Windows-only compiled converter |
| `Unity/` | C# editor scripts |
| `XSI/` | Softimage was discontinued in 2014 |
| `ZBrush/` | ZScript + compiled converters, export broken since ZBrush 2021.7 (upstream #59) |

The interchange format these implementations read and write is specified in
[`docs/FORMAT.md`](../docs/FORMAT.md); files they produce remain fully
supported by the maintained implementations.
