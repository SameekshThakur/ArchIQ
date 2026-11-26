@echo off
REM Starts the API and the web app in this window and opens the browser. Ctrl+C stops both.
setlocal
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo Setup has not been run yet. Run setup.bat first.
  exit /b 1
)
"backend\.venv\Scripts\python.exe" scripts\dev.py %*
