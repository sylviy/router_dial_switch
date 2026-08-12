@echo off
REM ==========================================================================
REM  smoke.bat  --  run the offline end-to-end self-test via the .venv.
REM  No router needed: it serves mock router pages on localhost and drives them
REM  with the real engine + the real model scripts.
REM  Needs Chrome installed (channel="chrome").  Add --show to watch it click.
REM  Expected result: "40 passed, 0 failed".
REM ==========================================================================
setlocal
pushd "%~dp0.."      REM 回到仓库根(本文件在 app\ 里)

call "%~dp0_py.bat"
if not defined PY (
  popd
  endlocal
  pause
  exit /b 1
)

"%PY%" "%~dp0..\tests\mock_test.py" %*
set "rc=%errorlevel%"
popd
endlocal
pause
exit /b %rc%
