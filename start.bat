@echo off
REM ==========================================================================
REM  start.bat  --  THE EASY BUTTON.  Double-click, pick a model by number,
REM  pick what to do, done.  Nothing to prepare, nothing to remember.
REM    start.bat setup   -- store router IP / passwords in router.yaml
REM  (Power users: dial.bat / matrix.bat still take arguments.)
REM ==========================================================================
setlocal
pushd "%~dp0"

call "%~dp0_py.bat"
if not defined PY (
  popd
  endlocal
  pause
  exit /b 1
)

"%PY%" start.py %*
set "rc=%errorlevel%"
popd
endlocal
pause
exit /b %rc%
