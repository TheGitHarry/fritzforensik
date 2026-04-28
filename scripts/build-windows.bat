@echo off
REM Lokaler PyInstaller-Build (Windows x86_64).
cd /d "%~dp0\.."
python -m pip install --quiet --upgrade "pyinstaller>=6" "certifi" "requests>=2.31" || exit /b 1
python scripts\build.py
