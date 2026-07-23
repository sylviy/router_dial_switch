@echo off
REM ==========================================================================
REM  matrix.bat  --  run the FULL WAN performance matrix via the .venv:
REM  switch dial mode -> wait for WAN -> throughput -> HTML+CSV report.
REM  All arguments are passed straight to run_matrix.py:
REM
REM    matrix.bat --list                      (list adapted models)
REM    matrix.bat --demo                      (offline demo: no router, sample report)
REM    matrix.bat --model Tenda_AX3000        (real run, does NOT save)
REM    matrix.bat --model Tenda_AX3000 --apply  (real run, really saves)
REM
REM  What/how to test lives in perf.yaml (copy perf.example.yaml); passwords
REM  live in router.yaml (run.bat setup).  Reports land in artifacts\.
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

".venv\Scripts\python.exe" run_matrix.py %*
set "rc=%errorlevel%"
popd
endlocal
pause
exit /b %rc%
