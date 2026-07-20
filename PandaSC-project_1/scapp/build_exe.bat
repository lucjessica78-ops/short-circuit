@echo off
REM Build PandaSC.exe on Windows.
REM Run this from the project root (the folder this file is in).
REM Requires Python 3.11 or 3.12 installed and on PATH.

echo Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo Building PandaSC.exe (this can take a few minutes)...
python -m PyInstaller build.spec --noconfirm
if errorlevel 1 goto :error

echo.
echo Done. Your executable is at dist\PandaSC.exe
echo Copy that single file to give to a customer -- it needs nothing else installed.
pause
exit /b 0

:error
echo.
echo Something went wrong -- see the errors above.
pause
exit /b 1
