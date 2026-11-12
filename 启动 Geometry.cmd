@echo off
chcp 65001 >nul
title Geometry - Local
cd /d "%~dp0geometry-app" || goto missing
if not exist ".venv\Scripts\python.exe" goto missing
if not exist "scripts\local.py" goto missing
echo 正在启动 Geometry，本机网页准备完成后会自动打开。
echo 使用期间请保留此窗口，关闭窗口即可结束本机服务。
echo 本机地址：http://127.0.0.1:3000/
"%~dp0geometry-app\.venv\Scripts\python.exe" -u "%~dp0geometry-app\scripts\local.py"
if errorlevel 1 pause
exit /b
:missing
echo Geometry files are missing. Keep this script beside the geometry-app folder.
pause
exit /b 1
