@echo off
REM ==========================================================================
REM  Vendor\py.bat  --  shared interpreter resolver.  Not meant to be
REM  double-clicked: each scene's .bat files `call` it and then use "%PY%".
REM
REM  It lives in Vendor\ on purpose -- %~dp0 IS the Vendor folder, so the paths
REM  below never count directory levels.  Move a scene deeper or rename it and
REM  this file still resolves.  Leaves PY empty (after explaining) when nothing
REM  usable is present, so each caller can bail out its own way.
REM
REM  Two supported runtimes, in this order:
REM    1) .venv\           -- built by a scene's setup.bat from a system 3.8+;
REM    2) Vendor\python\   -- the ready-to-run embedded Python 3.8 that ships
REM                           WITH the repo, for benches whose only Python is
REM                           an untouchable 2.x (see WINDOWS.md, way B).
REM
REM  There is deliberately NO fallback to a bare `python` on PATH: on exactly
REM  those benches `python` IS the Python 2 we must not touch, and the failure
REM  would surface as a baffling SyntaxError deep inside the tool.
REM ==========================================================================
set "PY="

if exist "%~dp0..\.venv\Scripts\python.exe" (
  set "PY=%~dp0..\.venv\Scripts\python.exe"
  goto :eof
)

if exist "%~dp0python\python.exe" (
  set "PY=%~dp0python\python.exe"
  goto :eof
)

echo [ERROR] No Python 3 runtime found in this repo.
echo.
echo   Expected one of:
echo     Vendor\python\python.exe   -- ships with the repo, nothing to install.
echo                                   Missing it means the folder was copied
echo                                   WITHOUT the Vendor\ subfolder.
echo     .venv\Scripts\python.exe   -- double-click a scene's app\setup.bat
echo                                   once to build it from a system 3.8+.
goto :eof
