@echo off
REM ==========================================================================
REM  adapt.bat  --  适配一台新路由器的向导。双击即可,不用记命令。
REM  探测页面 -> 生成 models\<品牌>_<型号>.py -> 体检 -> 逐个模式验证。
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

"%PY%" adapt.py
set "rc=%errorlevel%"
popd
endlocal
pause
exit /b %rc%
