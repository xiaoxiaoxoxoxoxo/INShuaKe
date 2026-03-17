@echo off
chcp 65001 >nul
title 刷课程序 - 目录模式打包（无控制台）
color 0A

echo ========================================
echo      刷课程序目录模式打包工具
echo ========================================
echo.

echo 步骤1: 设置环境变量...
set PLAYWRIGHT_BROWSERS_PATH=0
echo [OK] 环境变量已设置
echo.

echo 步骤2: 清理旧文件...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo [OK] 清理完成
echo.

echo 步骤3: 开始打包（窗口模式，无控制台）...
echo 正在打包，请耐心等待（约2-3分钟）...
echo.

pyinstaller --name="刷课程序_完整版" ^
            --onedir ^
            --noconsole ^
            --add-data="config;config" ^
            --add-data="templates;templates" ^
            --add-data="cdb.py;." ^
            --add-data="getcourseid.py;." ^
            --add-data="Shuake.py;." ^
            --add-data="gui_main.py;." ^
            --add-data="main.py;." ^
            --add-data="icon.ico;." ^
            --add-data="README.md;." ^
            --add-data="requirements.txt;." ^
            --add-data="start_gui.bat;." ^
            --add-data="courses.db;." ^
            --hidden-import=Shuake ^
            --hidden-import=getcourseid ^
            --hidden-import=cdb ^
            --hidden-import=gui_main ^
            --hidden-import=main ^
            --hidden-import=progressbar ^
            --hidden-import=cv2 ^
            --hidden-import=numpy ^
            --hidden-import=PIL ^
            --hidden-import=asyncio ^
            --hidden-import=requests ^
            --hidden-import=aiohttp ^
            --hidden-import=playwright ^
            --collect-all=playwright ^
            --collect-all=cv2 ^
            --collect-all=numpy ^
            --optimize=2 ^
            --clean ^
            gui_main.py

echo.
if %errorlevel% equ 0 (
    echo ========================================
    echo 打包成功！
    echo ========================================
    echo.
    echo 输出目录: dist\刷课程序_完整版\
    echo 程序已配置为无控制台窗口模式
    echo.
) else (
    echo 打包失败！
)

pause