@echo off
setlocal

REM Переходим в корень проекта (родитель deploy/)
cd /d "%~dp0.."

if not exist ".env" (
  echo [ERROR] Ne naiden .env v papke proekta: %cd%
  echo Skopiruyte .env.example v .env i zapolnite TELEGRAM_BOT_TOKEN.
  pause
  exit /b 1
)

echo Starting bot in new window...
if not exist ".cache" mkdir ".cache" >nul 2>&1

powershell -NoProfile -Command ^
  "$root = (Get-Location).Path; " ^
  "$p = Start-Process -FilePath cmd.exe -WorkingDirectory $root -ArgumentList '/k','title WikiLinkBot & set PYTHONUNBUFFERED=1 & python -m app.bot' -PassThru; " ^
  "$lockPath = Join-Path $root '.cache\cmd.lock'; " ^
  "[System.IO.File]::WriteAllText($lockPath, ([string]$p.Id + \"`r`n\"), [System.Text.Encoding]::ASCII); " ^
  "Write-Host ('Started cmd pid=' + $p.Id)"

echo Done.
