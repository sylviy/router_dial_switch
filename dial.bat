@echo off
REM ==========================================================================
REM  dial.bat  --  THE DAILY COMMAND: switch the WAN dial mode on an adapted
REM  model.  First argument is the model script name (without .py), the rest
REM  is passed straight through to it.
REM
REM    dial.bat Tenda_AX3000 dynamic          (switch only, does NOT save)
REM    dial.bat Tenda_AX3000 pppoe --apply    (really saves)
REM    dial.bat Cudy_AX l2tp --apply
REM    dial.bat                               (lists the available models)
REM
REM  Router IP / passwords come from router.yaml -- create it once with
REM  `run.bat setup`.  For a device with no script yet, use run.bat (cli.py).
REM ==========================================================================
setlocal
pushd "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found.  Double-click setup.bat first ^(one time^).
  goto :fail
)

if "%~1"=="" (
  echo Usage: dial.bat ^<Model^> ^<mode^> [--apply]
  echo.
  echo Available models:
  for %%F in (models\*.py) do call :listone "%%~nF"
  echo.
  echo Example:  dial.bat Tenda_AX3000 pppoe --apply
  goto :fail
)

if not exist "models\%~1.py" (
  echo [ERROR] No such model script: models\%~1.py
  echo         Run dial.bat with no arguments to list the available models.
  goto :fail
)

set "MODEL=%~1"
shift

REM batch has no "all args except the first" -- rebuild it by hand
set "ARGS="
:collect
if "%~1"=="" goto :run
set "ARGS=%ARGS% %1"
shift
goto :collect

:run
".venv\Scripts\python.exe" "models\%MODEL%.py"%ARGS%
set "rc=%errorlevel%"
popd
endlocal
exit /b %rc%

REM --- helper: print a model name unless it starts with "_" ------------------
:listone
set "N=%~1"
if "%N:~0,1%"=="_" goto :eof
echo    %N%
goto :eof

:fail
popd
endlocal
pause
exit /b 1
