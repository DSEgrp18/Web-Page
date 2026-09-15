@echo off
rem Update the running reader with the latest code: .\refresh
rem Options are passed through, for example: .\refresh -Only web
rem Runs scripts\refresh.ps1 without changing the machine's PowerShell policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\refresh.ps1" %*
