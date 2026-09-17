@echo off
setlocal
cd /d "%~dp0"

set PYEXE=
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 set PYEXE=py -3

if not defined PYEXE (
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 set PYEXE=python
)

if not defined PYEXE (
    echo Python was not found on PATH.
    echo Install Python 3.11 or newer from https://www.python.org/downloads/ and re-run this script.
    pause
    exit /b 1
)

%PYEXE% "scripts\run.py" %*
set EXITCODE=%ERRORLEVEL%
if not %EXITCODE%==0 (
    echo.
    echo run.bat exited with code %EXITCODE%. See the message above for details.
    pause
)
exit /b %EXITCODE%
