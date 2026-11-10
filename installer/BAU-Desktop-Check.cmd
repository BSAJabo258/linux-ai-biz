@echo off
rem BAU desktop check for Windows: double-click this file (keep it next to
rem bau-laptop-check.ps1, the same read-only check as the laptop one; it also names the
rem graphics cards and the free disk). It asks for administrator rights, runs the check,
rem then opens the summary to send. It changes nothing on this PC.
net session >nul 2>&1
if errorlevel 1 (
  echo Asking for administrator rights: click Yes.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
cd /d "%~dp0"
if not exist "%~dp0bau-laptop-check.ps1" (
  echo bau-laptop-check.ps1 must be in the same folder as this file: %~dp0
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0bau-laptop-check.ps1" -Out "%~dp0BAU-Desktop-Check"
if exist "%~dp0BAU-Desktop-Check\BAU-LAPTOP-SUMMARY.txt" start "" notepad "%~dp0BAU-Desktop-Check\BAU-LAPTOP-SUMMARY.txt"
echo.
echo Done. Send BAU-LAPTOP-SUMMARY.txt from %~dp0BAU-Desktop-Check
pause
