@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
title AgentRelay portable
cd /d "%~dp0" || exit /b 1

echo AgentRelay portable
echo Directory: "%CD%"

set "PY="
if defined RELAY_PYTHON call :candidate "%RELAY_PYTHON%"
if not defined PY call :candidate "%CD%\runtime\python\python.exe"
if not defined PY call :candidate "%CD%\runtime\python\Scripts\python.exe"
if not defined PY call :candidate "%CD%\runtime\python.exe"
if not defined PY for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do call :candidate "%%P"
if not defined PY for /f "delims=" %%P in ('where python 2^>nul') do call :candidate "%%P"
if not defined PY for /f "delims=" %%P in ('where python3 2^>nul') do call :candidate "%%P"
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :candidate "%%D\python.exe"
if not defined PY goto :nopy

echo Python: "%PY%"
REM -c adds app/ to sys.path even for the Windows embeddable runtime.
"%PY%" -c "import runpy,sys;sys.path.insert(0,'app');runpy.run_path('app/bootstrap.py',run_name='__main__')"
if errorlevel 1 goto :failed
"%PY%" -c "import runpy,sys;sys.path.insert(0,'app');runpy.run_path('app/cli.py',run_name='__main__')" serve
if errorlevel 1 goto :failed
exit /b 0

:candidate
if defined PY exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys;raise SystemExit(0 if sys.version_info >= (3,8) else 1)" >nul 2>nul
if errorlevel 1 exit /b 0
set "PY=%~1"
exit /b 0

:nopy
echo No usable Python 3.8+ found.
echo Install Python from https://www.python.org/downloads/
echo Or extract the Windows embeddable package to runtime\python\
echo You may also set RELAY_PYTHON to the full path of python.exe.
pause
exit /b 1

:failed
echo AgentRelay exited with an error. See the message above.
pause
exit /b 1
