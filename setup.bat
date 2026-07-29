@echo off
REM ==========================================================================
REM  setup.bat  --  one-time setup on a Windows machine.  Double-click it.
REM
REM  Works in ALL THREE situations:
REM    A) the repo as downloaded from GitHub -> vendor\python already carries
REM       an embedded Python 3.8 with the dependencies pre-installed, so there
REM       is NOTHING to install: this script only verifies it and stops.  That
REM       is the offline-bench case (the bench's own Python 2 is never touched);
REM    B) vendor\wheels present but no pre-installed runtime -> build a .venv
REM       and install the deps from those wheels, still without internet;
REM    C) no vendor\ at all (e.g. someone pruned it) -> use the Python already
REM       installed on the machine and download the deps with pip.
REM
REM  Note: everything below runs from this folder (pushd), so the interpreter
REM  is referenced by a RELATIVE path -- that keeps working even when the
REM  folder lives under a path with spaces, e.g. C:\Users\Li Ming\Desktop\.
REM ==========================================================================
setlocal
pushd "%~dp0"

set "PY="
set "MODE="

REM --- A) ready-to-run runtime shipped with the repo: verify and stop --------
if exist "vendor\python\Lib\site-packages\playwright" (
  echo === Ready-to-run runtime found in vendor\python -- nothing to install ===
  "vendor\python\python.exe" -c "import sys, playwright.sync_api, yaml; print('imports OK on Python ' + sys.version.split()[0])"
  if errorlevel 1 (
    echo.
    echo [ERROR] The bundled runtime is there but did not import.
    echo         Usually that means the folder was copied without vendor\
    echo         intact -- re-copy the WHOLE folder and try again.
    goto :fail
  )
  goto :done
)

if exist "vendor\python\python.exe" (
  set "PY=vendor\python\python.exe"
  set "MODE=bundled Python 3.8 in vendor\python"
  goto :havepy
)

REM --- no bundle: look for a system Python 3.8+ -------------------------------
set "PY=py -3"
%PY% -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,8) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "MODE=system Python via the py launcher"
  goto :havepy
)

set "PY=python"
%PY% -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3,8) else 1)" >nul 2>&1
if not errorlevel 1 (
  set "MODE=system Python on PATH"
  goto :havepy
)

echo [ERROR] No usable Python found ^(need 3.8 or newer^).
echo.
echo   Fix it one of these ways:
echo     * install Python from https://www.python.org/downloads/windows/
echo       and TICK "Add python.exe to PATH" in the installer, then re-run me;
echo     * or use the offline USB bundle, which carries its own Python:
echo       copy the whole folder INCLUDING vendor\ over and double-click me.
goto :fail

:havepy
echo === Step 1/3: creating .venv using %MODE% ===
%PY% -m venv .venv
if errorlevel 1 (
  echo [ERROR] Could not create .venv.
  goto :fail
)

echo.
if exist "vendor\wheels" (
  echo === Step 2/3: installing dependencies from vendor\wheels ^(offline^) ===
  ".venv\Scripts\python.exe" -m pip install --no-index --find-links "vendor\wheels" -r requirements.txt
) else (
  echo === Step 2/3: installing dependencies with pip ^(needs internet^) ===
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
if errorlevel 1 (
  echo [ERROR] Dependency install failed.
  echo         Online?  check the connection / company proxy.
  echo         Offline? make sure the vendor\wheels folder came along too.
  goto :fail
)

echo.
echo === Step 3/3: verifying the imports work ===
".venv\Scripts\python.exe" -c "import playwright.sync_api, yaml; print('imports OK')"
if errorlevel 1 goto :fail

:done
echo.
echo ============================================================
echo   SETUP COMPLETE.
echo.
echo   Easiest from here: double-click start.bat ^(pick a model by
echo   number, Enter = the full round^).  Or, from the command line:
echo.
echo   1^) store router IP / passwords once:
echo        start.bat  ^-^> menu 4
echo   2^) switch the dial mode on an adapted model:
echo        dial.bat Tenda_AX3000 pppoe      ^(add --apply to really save^)
echo        dial.bat Cudy_AX1500 dynamic
echo   3^) offline self-test ^(needs Chrome installed^):
echo        smoke.bat
echo ============================================================
popd
endlocal
exit /b 0

:fail
echo.
echo *** SETUP FAILED -- read the messages above. ***
echo     ^( Nothing was installed system-wide; fix it and just run me again. ^)
popd
endlocal
pause
exit /b 1
