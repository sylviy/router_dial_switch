@echo off
REM ==========================================================================
REM  matrix.bat  --  run the FULL WAN performance matrix via the .venv:
REM  switch dial mode -> wait for WAN -> throughput -> HTML+CSV report.
REM  All arguments are passed straight to run_matrix.py:
REM
REM    matrix.bat --list                      (list adapted models)
REM    matrix.bat --demo                      (offline demo: no router, sample report)
REM    matrix.bat --model Tenda_AX3000        (real run: every declared mode,
REM                                            each one really applied)
REM
REM  What/how to test lives in perf.yaml (copy perf.example.yaml); passwords
REM  live in router.yaml (start.bat menu 4).  Reports land in artifacts\.
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

"%PY%" run_matrix.py %*
set "rc=%errorlevel%"
popd
endlocal
pause
exit /b %rc%
