@echo off
REM AgentRelay 便携版 · Windows 启动器
REM 整个目录可以放在任意盘符的移动硬盘里路径也随便换，这里全部相对本文件解析。

setlocal enabledelayedexpansion
chcp 65001 >nul
title AgentRelay 便携版

cd /d "%~dp0"

echo.
echo   AgentRelay 便携版
echo   目录： %CD%
echo.

REM ---- 1. 找 Python ----
set "PY="

REM 1a. 盘上自带的 runtime（优先，真正做到免安装）
if exist "%CD%\runtime\python\python.exe" (
    set "PY=%CD%\runtime\python\python.exe"
    set "PYFROM=移动硬盘自带"
)

REM 1b. Windows py 启动器
if not defined PY (
    where py >nul 2>nul
    if !errorlevel!==0 (
        py -3 -c "import sys" >nul 2>nul
        if !errorlevel!==0 (
            set "PY=py -3"
            set "PYFROM=Windows Python 启动器"
        )
    )
)

REM 1c. PATH 里的 python / python3
if not defined PY (
    where python >nul 2>nul
    if !errorlevel!==0 (
        set "PY=python"
        set "PYFROM=PATH 中的 python"
    )
)
if not defined PY (
    where python3 >nul 2>nul
    if !errorlevel!==0 (
        set "PY=python3"
        set "PYFROM=PATH 中的 python3"
    )
)

if not defined PY goto :nopy

echo   找到 Python：!PYFROM!
echo.

REM ---- 2. 环境体检（顺带验证版本够不够） ----
!PY! "%CD%\app\bootstrap.py"
if errorlevel 2 goto :badpy

echo.
echo   正在启动 Web 界面，浏览器会自动打开。
echo   用完直接关掉这个窗口即可停止服务。
echo.
pause

start "" http://127.0.0.1:8745
!PY! "%CD%\app\cli.py" serve

if errorlevel 1 (
    echo.
    echo   服务异常退出。
    pause
)
goto :eof

:nopy
echo   [×] 这台机器上没有找到 Python
echo.
echo   两种解决办法（推荐第一种）：
echo.
echo   1. 把 Python 嵌入式版放进 U 盘的 runtime\python\ 目录
echo      下载地址： python.org 搜 "Windows embeddable package" (64-bit)
echo      解压后应存在： %CD%\runtime\python\python.exe
echo.
echo   2. 在这台机器上安装 Python（安装时勾选 Add Python to PATH）
echo      https://www.python.org/downloads/
echo.
echo   然后重新双击本文件。
echo.
pause
goto :eof

:badpy
echo.
echo   [×] Python 版本过低，需要 3.8 以上。请换一个新版本。
echo.
pause
goto :eof
