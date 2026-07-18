@echo off
REM ==========================================================================
REM  setup.bat  --  one-time setup on a Windows machine.  Double-click it.
REM
REM  Works in BOTH situations:
REM    A) plain download from GitHub (no vendor\ folder)  -> uses the Python
REM       already installed on the machine and downloads the deps with pip;
REM    B) the offline USB bundle (vendor\python + vendor\wheels present)
REM       -> uses the BUNDLED Python 3.8 and installs from vendor\wheels, so
REM          the machine's locked system Python is never touched and no
REM          internet is needed.
REM  Either way you end up with an isolated .venv inside this folder.
REM
REM  Note: everything below runs from this folder (pushd), so the interpreter
REM  is referenced by a RELATIVE path -- that keeps working even when the
REM  folder lives under a path with spaces, e.g. C:\Users\Li Ming\Desktop\.
REM ==========================================================================
setlocal
pushd "%~dp0"

set "PY="
set "MODE="

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

echo.
echo ============================================================
echo   SETUP COMPLETE.
echo.
echo   1^) store router IP / passwords once:
echo        run.bat setup
echo   2^) switch the dial mode on an adapted model:
echo        dial.bat Tenda_AX3000 pppoe      ^(add --apply to really save^)
echo        dial.bat Cudy_AX dynamic
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
