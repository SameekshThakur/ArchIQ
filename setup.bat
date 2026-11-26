@echo off
REM One-time setup for Windows (no `make` needed). Requires Python 3.11+ and Node 22.9+.
setlocal
cd /d "%~dp0"

REM Find a real Python. "py -3" is the reliable launcher; plain "python" can be a Microsoft Store stub that does nothing.
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY goto :nopython

where node >nul 2>&1 || goto :nonode
where npm >nul 2>&1 || goto :nonode

echo [1/3] Creating the Python environment...
cd /d "%~dp0backend"
%PY% -m venv .venv || goto :err
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
echo [2/3] Installing backend packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :err
echo [3/3] Installing frontend packages (this takes a few minutes)...
cd /d "%~dp0frontend"
call npm install || goto :err
echo.
cd /d "%~dp0"
"backend\.venv\Scripts\python.exe" scripts\doctor.py
echo.
echo Setup complete. Now run dev.bat
exit /b 0

:nopython
echo Python 3.11 or newer was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH", then run setup.bat again.
echo (If "python" opens the Microsoft Store, turn off App execution aliases for python.exe in Windows Settings.)
exit /b 1

:nonode
echo Node.js 22.9 or newer was not found. Install the LTS version from https://nodejs.org, open a NEW terminal, and run setup.bat again.
exit /b 1

:err
echo.
echo Setup failed. Scroll up for the first error message. Run "python scripts\doctor.py" for a checklist.
exit /b 1
