@echo off
REM ==========================================================================
REM  smoke.bat  --  run the offline end-to-end self-test via the .venv.
REM  No router needed: it serves mock router pages on localhost and drives them
REM  with the real engine + the real model scripts.
REM  Needs Chrome installed (channel="chrome").  Add --show to watch it click.
REM  Expected result: "37 passed, 0 failed".
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
