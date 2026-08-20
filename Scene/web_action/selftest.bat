@echo off
REM ==========================================================================
REM  selftest.bat  --  这个场景的离线自检。不需要设备:本地起一个假设备页,
REM  用真的浏览器 + 真的 Tools\act.py 跑一遍。
REM  期望结果:"11 passed, 0 failed"。加 --show 可以看着它点。
REM ==========================================================================
setlocal
pushd "%~dp0"

call "%~dp0..\..\Vendor\py.bat"
if not defined PY (
  popd
  endlocal
  pause
  exit /b 1
)

"%PY%" tests\mock_test.py %*
set "rc=%errorlevel%"
popd
endlocal
pause
exit /b %rc%
