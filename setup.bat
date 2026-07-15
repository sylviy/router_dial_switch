@echo off
REM ==========================================================================
REM  setup.bat  --  one-time, OFFLINE setup on the Windows company computer.
REM  Builds an isolated .venv from the BUNDLED Python 3.8 in vendor\python
REM  (so the machine's locked/old system Python is never touched) and installs
REM  every dependency from the vendored wheels in vendor\wheels -- no internet.
REM  Just double-click this file once after copying the whole folder over.
REM ==========================================================================
setlocal
pushd "%~dp0"

set "PYEXE=%~dp0vendor\python\python.exe"
if not exist "%PYEXE%" (
  echo [ERROR] Bundled Python not found at:
  echo         "%PYEXE%"
  echo         Make sure the ENTIRE folder ^(including the vendor\ subfolder^)
  echo         was copied over, not just the .py files.
  goto :fail
)

echo === Step 1/3: building .venv from the bundled Python 3.8 ===
"%PYEXE%" -m venv .venv
if errorlevel 1 goto :fail

echo.
echo === Step 2/3: installing dependencies from vendored wheels (offline) ===
".venv\Scripts\python.exe" -m pip install --no-index --find-links "vendor\wheels" -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo === Step 3/3: verifying the imports work ===
".venv\Scripts\python.exe" -c "import playwright.sync_api, yaml; print('imports OK')"
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo   SETUP COMPLETE.
echo   Run the tool with, e.g.:
echo     run.bat --router-ip 192.168.1.1 --pass PW --mode pppoe ^^
echo             --param pppoe_user=x --param pppoe_pass=y --no-apply
echo   Offline self-test (needs Chrome installed):  smoke.bat
echo ============================================================
popd
endlocal
exit /b 0

:fail
echo.
echo *** SETUP FAILED -- read the messages above. ***
echo     ( Nothing was installed system-wide; you can just fix and re-run. )
popd
endlocal
pause
exit /b 1
