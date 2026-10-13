@echo off
rem BAU keys export for Windows: double-click this file, or drop .env files onto it.
rem Keep it next to bau-keys-export.ps1. It finds your API keys, shows their names only,
rem and locks them into BAU-KEYS.enc with a passphrase you choose. It changes nothing here.
cd /d "%~dp0"
if not exist "%~dp0bau-keys-export.ps1" (
  echo bau-keys-export.ps1 must be in the same folder as this file: %~dp0
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bau-keys-export.ps1" -Out "%~dp0BAU-KEYS.enc" %*
echo.
pause
