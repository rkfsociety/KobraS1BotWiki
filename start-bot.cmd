@echo off
setlocal

cd /d "%~dp0"

if not exist ".env" (
  echo [ERROR] Ne naiden .env v papke proekta: %cd%
  echo Skopiruyte .env.example v .env i zapolnite TELEGRAM_BOT_TOKEN.
  pause
  exit /b 1
)

echo Starting bot in new window...
REM Стартуем через PowerShell, чтобы получить PID окна cmd и уметь его закрывать.
if not exist ".cache" mkdir ".cache" >nul 2>&1

powershell -NoProfile -Command ^
  "Set-Location '%~dp0'; if(!(Test-Path '.cache')){ New-Item -ItemType Directory -Path '.cache' | Out-Null }; " ^
  "$p = Start-Process -FilePath cmd.exe -WorkingDirectory '%~dp0' -ArgumentList '/k','title WikiLinkBot & set PYTHONUNBUFFERED=1 & python -m app.bot' -PassThru; " ^
  "$lockPath = Join-Path (Get-Location) '.cache\\cmd.lock'; " ^
  "[System.IO.File]::WriteAllText($lockPath, ([string]$p.Id + \"`r`n\"), [System.Text.Encoding]::ASCII); " ^
  "Write-Host ('Started cmd pid=' + $p.Id)"

echo Done.
