@echo off
REM ==========================================================================
REM  start.bat  --  唯一入口。双击它,选型号、选操作,没有别的要记。
REM
REM  这个目录下只有两样东西是给人碰的:
REM     start.bat     双击我
REM     config.yaml   用记事本改(缺什么菜单 5 会连行号一起告诉你)
REM  其余目录:app\ 程序入口 / docs\ 文档 / models\ 每台机一个脚本 /
REM            artifacts\ 报告和截图 / vendor\ 离线运行时(别动)
REM ==========================================================================
setlocal
pushd "%~dp0"

call "%~dp0app\_py.bat"
if not defined PY (
  popd
  endlocal
  pause
  exit /b 1
)

"%PY%" app\start.py
set "rc=%errorlevel%"
popd
endlocal
pause
exit /b %rc%
