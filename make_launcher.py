# -*- coding: utf-8 -*-
"""生成「启动实时服务.bat」（GBK 编码 + CRLF 换行，cmd 才不会乱码/秒退）"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

BAT = r"""@echo off
chcp 936 >nul
cd /d "%~dp0"

echo ============================================
echo   创作广场 - 实时直连服务（双击启动）
echo ============================================
echo.

set PYCMD=python
%PYCMD% --version >nul 2>&1
if errorlevel 1 set PYCMD="C:\Users\张炼鑫\.workbuddy\binaries\python\versions\3.13.12\python.exe"
%PYCMD% --version >nul 2>&1
if errorlevel 1 (
  echo [错误] 没找到 Python，请先安装 Python 3
  echo [提示] 安装时记得勾选 Add Python to PATH
  echo.
  pause
  exit /b
)

echo [正在启动] 创作广场实时服务
echo [电脑打开] http://127.0.0.1:8788/
echo [手机打开] 把 127.0.0.1 换成这台电脑的局域网 IP，端口 8788
echo [停止服务] 直接关闭弹出的服务窗口即可
echo.

start "创作广场实时服务" cmd /k %PYCMD% server.py

timeout /t 2 >nul
start "" http://127.0.0.1:8788/

echo [已启动] 浏览器已打开，关掉服务窗口才会停服务
echo.
pause
"""


def main():
    p = os.path.join(ROOT, "启动实时服务.bat")
    with open(p, "wb") as f:
        f.write(BAT.replace("\n", "\r\n").encode("gbk"))
    print("written:", p, os.path.getsize(p), "bytes")


if __name__ == "__main__":
    main()
