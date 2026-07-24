@echo off
REM Lokaler PyInstaller-Build (Windows x86_64).
REM   scripts\build-windows.bat [export^|report^|all]   (Default: all)
cd /d "%~dp0\.."
set TOOL=%1
if "%TOOL%"=="" set TOOL=all
python -m pip install --quiet --upgrade "pyinstaller>=6" "certifi" "requests>=2.31" || exit /b 1
python scripts\build.py --tool %TOOL%
