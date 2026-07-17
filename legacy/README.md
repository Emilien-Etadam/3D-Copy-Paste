# Legacy implementations

Everything in this directory is **unmaintained upstream code**, kept verbatim
from the abandoned original project
([heimlich1024/OD_CopyPasteExternal](https://github.com/heimlich1024/OD_CopyPasteExternal))
for reference and for users whose pipelines still depend on it. None of it is
tested, fixed, or supported as-is; see [`docs/AUDIT.md`](../docs/AUDIT.md)
for the state of each (findings and upstream issue numbers).

Several of these are **scheduled for repair** in the fork's roadmap and will
graduate back to the repository root once rewritten and tested — in the
meantime the versions here are the historical upstream code.

| Directory | State | Plan |
|---|---|---|
| `3DCoat/` | Works on Windows via compiled `.exe` converters | Stays; the cross-platform OBJ converter CLI replaces the `.exe` route |
| `Blender/` | Superseded by the extension in [`../Blender/`](../Blender/) | Kept for history |
| `SubstancePainter/` | Paste-only, Windows-only compiled converter | Stays; OBJ converter CLI replaces the `.exe` route |
| `Unity/` | Works (C# editor scripts) | Stays as-is |

Removed from the tree (recoverable from git history, deleted in the 2026-07
re-scoping because the host applications are discontinued): **XSI**
(Softimage ended 2014), **Modo** (end-of-life announced by Foundry, kit broken
on 16.1+, upstream #71), **Lightwave** (Python 2 SDK, upstream PR #73
abandoned). The Modo kit was the format's historical reference
implementation; the format itself is preserved in
[`docs/FORMAT.md`](../docs/FORMAT.md), and files written by those
applications still paste correctly everywhere — backward compatibility of
the format is unaffected by their removal.
