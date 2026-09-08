@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe"
if not exist "%PY%" set "PY=python"

set /p "START_ISSUE=请输入起始期数: "
set /p "END_ISSUE=请输入结束期数: "
if "%START_ISSUE%"=="" exit /b 2
if "%END_ISSUE%"=="" exit /b 2

"%PY%" run_v2.py crawl-range "%START_ISSUE%" "%END_ISSUE%"

echo.
pause
