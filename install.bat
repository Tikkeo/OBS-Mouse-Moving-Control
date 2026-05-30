@echo off
echo 正在安装OBS屏幕鼠标控制插件依赖...
echo.

pip install -r requirements.txt

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo 依赖安装成功！
    echo ========================================
    echo.
    echo 下一步：
    echo 1. 打开OBS Studio
    echo 2. 进入 工具 -^> 脚本
    echo 3. 点击 + 号，添加 screen-mouse-controller.py
    echo.
) else (
    echo.
    echo ========================================
    echo 依赖安装失败，请检查Python是否正确安装
    echo ========================================
    echo.
)

pause
