@echo off
REM ==========================================================================
REM  smoke.bat  --  run the offline end-to-end self-test via the .venv.
REM  Needs Chrome installed (channel="chrome").  Add --show to watch it click.
REM  Expected result: "15 passed, 0 failed".
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

".venv\Scripts\python.exe" tests\smoke_test.py %*
set "rc=%errorlevel%"
popd
endlocal
pause
exit /b %rc%
