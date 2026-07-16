@echo off
REM ==========================================================================
REM  run.bat  --  run the dial-switch tool via the isolated .venv.
REM  Forwards all arguments straight to cli.py.  Examples:
REM    run.bat setup            (one time: writes router.yaml with IP/passwords)
REM    run.bat pppoe            (adaptation phase / unscripted device)
REM    run.bat dynamic
REM  Daily use on an ADAPTED model goes through its own script instead:
REM    .venv\Scripts\python.exe models\Tenda_AX3000.py pppoe
REM    .venv\Scripts\python.exe models\Tenda_AX3000.py dynamic --apply
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
