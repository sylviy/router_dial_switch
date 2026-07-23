@echo off
REM ==========================================================================
REM  start.bat  --  THE EASY BUTTON.  Double-click, pick a model by number,
REM  pick what to do, done.  Nothing to prepare, nothing to remember.
REM  (Power users: dial.bat / matrix.bat / run.bat still take arguments.)
REM ==========================================================================
setlocal
pushd "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found.  Double-click setup.bat first ^(one time^).
  popd
  endlocal
  pause
  exit /b 1
)

".venv\Scripts\python.exe" start.py
set "rc=%errorlevel%"
popd
endlocal
pause
exit /b %rc%
