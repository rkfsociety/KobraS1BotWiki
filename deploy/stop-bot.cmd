@echo off
setlocal EnableDelayedExpansion

REM Переходим в корень проекта (родитель deploy/)
cd /d "%~dp0.."

set "LOCK=.cache\bot.lock"
set "CMDLOCK=.cache\cmd.lock"
if not exist "%LOCK%" (
  echo Lock file not found: %LOCK%
  echo If bot is still running, close its window or kill python.exe manually.
  exit /b 0
)

set /p PID=<"%LOCK%"
echo Stopping bot pid=%PID% ...

taskkill /F /T /PID %PID% >nul 2>&1

if exist "%CMDLOCK%" (
  echo Found cmd lock file: %CMDLOCK%
)
if exist "%CMDLOCK%" (
  set /p CMDPID=<"%CMDLOCK%"
  if not "!CMDPID!"=="" (
    echo Closing cmd window pid=!CMDPID! ...
    taskkill /F /T /PID !CMDPID!
  )
  del "%CMDLOCK%" >nul 2>&1
)

taskkill /F /T /FI "WINDOWTITLE eq WikiLinkBot" >nul 2>&1

del "%LOCK%" >nul 2>&1
echo Done.
