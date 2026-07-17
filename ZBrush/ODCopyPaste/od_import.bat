@echo off
rem OD_CopyPasteExternal - convert the exchange file to 1.OBJ for ZBrush import
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 od_zbrush_convert.py import
) else (
    python od_zbrush_convert.py import
)
