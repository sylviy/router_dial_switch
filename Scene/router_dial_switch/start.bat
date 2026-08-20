@echo off
REM ==========================================================================
REM  start.bat  --  这个场景的入口。双击它,选型号、选操作,没有别的要记。
REM
REM  这个目录下只有两样东西是给人碰的:
REM     start.bat     双击我
REM     config.yaml   用记事本改(缺什么菜单 5 会连行号一起告诉你)
REM  其余:app\ 程序入口 / Models\ 每台机一个目录 / matrix\ 测吞吐出报告 /
REM        tests\ 离线自检 / docs\ 文档 / artifacts\ 报告和截图
REM  公共库和离线 Python 在仓库根的 Vendor\,通用探针在 Tools\(都别动)。
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

"%PY%" app\start.py
set "rc=%errorlevel%"
popd
endlocal
pause
exit /b %rc%
