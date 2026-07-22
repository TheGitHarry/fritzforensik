@echo off
REM Lokaler PyInstaller-Build (Windows x86_64). stdlib-only.
cd /d "%~dp0\.."
python -m pip install --quiet --upgrade "pyinstaller>=6"
python scripts\build.py
