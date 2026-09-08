@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe"
if not exist "%PY%" set "PY=python"

set /p "ISSUE=请输入要抓取的期数: "
set "RESULT=未输入期数，未执行抓取。"
if "%ISSUE%"=="" goto :finish

"%PY%" run_v2.py crawl "%ISSUE%"
set "RESULT=抓取失败，请查看上方提示。"
if errorlevel 1 goto :finish
set "RESULT=抓取完成。"

:finish
echo.
echo %RESULT%
pause
endlocal
