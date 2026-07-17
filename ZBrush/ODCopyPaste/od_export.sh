#!/bin/sh
# OD_CopyPasteExternal - convert ZBrush's exported 1.OBJ to the exchange file
cd "$(dirname "$0")" || exit 1
exec python3 od_zbrush_convert.py export
