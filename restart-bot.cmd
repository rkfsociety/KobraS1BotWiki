@echo off
setlocal

cd /d "%~dp0"

echo Restarting bot...
call "%~dp0stop-bot.cmd"
timeout /t 1 /nobreak >nul
call "%~dp0start-bot.cmd"

echo Done.
