@echo off
rem BAU Pack maker for Windows: double-click this file. Keep it next to bau-pack-make.ps1.
rem It asks which USB stick to use, then downloads the BAU laptop's AI models onto it
rem (each checked against its pinned SHA-256). It never formats or erases anything.
cd /d "%~dp0"
if not exist "%~dp0bau-pack-make.ps1" (
  echo bau-pack-make.ps1 must be in the same folder as this file: %~dp0
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bau-pack-make.ps1" %*
echo.
pause
