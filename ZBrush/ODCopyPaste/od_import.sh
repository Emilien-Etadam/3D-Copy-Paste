#!/bin/sh
# OD_CopyPasteExternal - convert the exchange file to 1.OBJ for ZBrush import
cd "$(dirname "$0")" || exit 1
exec python3 od_zbrush_convert.py import
