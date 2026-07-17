@echo off
rem OD_CopyPasteExternal - convert ZBrush's exported 1.OBJ to the exchange file
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 od_zbrush_convert.py export
) else (
    python od_zbrush_convert.py export
)
