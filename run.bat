@echo off
REM ==========================================================================
REM  run.bat  --  the ADAPTATION toolbox (cli.py) via the isolated .venv.
REM  Forwards all arguments straight to cli.py.  Examples:
REM    run.bat setup            (one time: writes router.yaml with IP/passwords)
REM    run.bat diagnose         (evidence dump for a device with no script yet)
REM    run.bat pppoe            (heuristic attempt on an unscripted device)
REM
REM  DAILY USE on an already-adapted model is dial.bat, not this:
REM    dial.bat Tenda_AX3000 pppoe --apply
REM
REM  Long form still works:
REM    run.bat --router-ip 192.168.1.1 --pass PW --mode pppoe ^
REM            --param pppoe_user=x --param pppoe_pass=y --no-apply
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

".venv\Scripts\python.exe" cli.py %*
set "rc=%errorlevel%"
popd
endlocal
exit /b %rc%
