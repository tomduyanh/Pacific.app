@echo off
setlocal
title Pacific Desktop
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if defined PY goto :haspy
where python >nul 2>nul && set "PY=python"
if defined PY goto :haspy
where py >nul 2>nul && set "PY=py"

:haspy
if not defined PY goto :nopy

"%PY%" run.py --desktop %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo   Pacific Desktop exited with code %RC%.
  pause
)
exit /b %RC%

:nopy
echo.
echo   [!] Python was not found on this machine.
echo       Install Python 3.9+ from https://www.python.org/downloads/
echo.
pause
exit /b 1
