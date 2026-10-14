@echo off
cd /d "%~dp0"
title Speaking Coach
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 server.py
) else (
  python server.py
)
echo.
echo The server has stopped. Press any key to close this window.
pause >nul
