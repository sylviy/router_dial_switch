@echo off
REM ==========================================================================
REM  _py.bat  --  shared interpreter resolver.  Not meant to be double-clicked:
REM  the other .bat files `call` it (paths inside are anchored to this file's
REM  own folder, so it works no matter what the caller pushd'd), then use "%PY%".  Leaves PY empty (after explaining) when nothing usable
REM  is present, so each caller can bail out its own way.
REM
REM  Two supported runtimes, in this order:
REM    1) .venv\           -- built by setup.bat from a system Python 3.8+;
REM    2) vendor\python\   -- the ready-to-run embedded Python 3.8 that ships
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

if exist "%~dp0..\vendor\python\python.exe" (
  set "PY=%~dp0..\vendor\python\python.exe"
  goto :eof
)

echo [ERROR] No Python 3 runtime found in this folder.
echo.
echo   Expected one of:
echo     vendor\python\python.exe   -- ships with the repo, nothing to install.
echo                                   Missing it means the folder was copied
echo                                   WITHOUT the vendor\ subfolder.
echo     .venv\Scripts\python.exe   -- double-click setup.bat once to build it
echo                                   from a system Python 3.8+.
goto :eof
