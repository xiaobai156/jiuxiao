@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=%~dp0.paddleocr-cpu-venv\Scripts\python.exe"
if not exist "%PY%" goto :env_missing
call :validate_paddle_env
if errorlevel 1 goto :env_invalid

set /p "START_ISSUE=请输入起始期数: "
set /p "END_ISSUE=请输入结束期数: "
if "%START_ISSUE%"=="" exit /b 2
if "%END_ISSUE%"=="" exit /b 2

"%PY%" run_v2.py crawl-range "%START_ISSUE%" "%END_ISSUE%"

echo.
pause
exit /b

:env_missing
echo [错误] 项目专属 PaddleOCR CPU 虚拟环境不存在：
echo         %~dp0.paddleocr-cpu-venv
echo         请先运行“安装-PaddleOCR-CPU环境.bat”。
pause
exit /b 1

:env_invalid
echo [错误] 项目专属 PaddleOCR CPU 依赖验证失败，已停止抓取。
echo         请先运行“安装-PaddleOCR-CPU环境.bat”修复本地环境。
pause
exit /b 1

:validate_paddle_env
"%PY%" -c "import importlib.metadata as md; import pathlib; import sys; import paddle; import paddleocr; import google.protobuf; expected={'paddlepaddle':'3.2.0','paddleocr':'3.5.0','protobuf':'3.20.2'}; actual={name: md.version(name) for name in expected}; proto_path=pathlib.Path(google.protobuf.__file__).resolve(); venv_path=pathlib.Path(sys.prefix).resolve(); device=''; error=''; error = 'Python 版本不是 3.10' if tuple(sys.version_info[:2]) != (3, 10) else ''; error = '依赖版本不匹配: ' + repr(actual) if not error and actual != expected else error; error = 'protobuf 未从项目虚拟环境加载: ' + str(proto_path) if not error and venv_path not in proto_path.parents else error; paddle.set_device('cpu'); device=str(paddle.device.get_device()).lower(); error = 'Paddle 设备不是 CPU: ' + device if not error and device != 'cpu' else error; assert not error, error; print('PaddleOCR CPU 依赖验证通过。')"
exit /b %ERRORLEVEL%
