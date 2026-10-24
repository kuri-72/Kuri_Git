@echo off
chcp 65001 >nul 2>&1
title XIAO72 VOICE
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set HF_HUB_DISABLE_XET=1
set HF_ENDPOINT=https://huggingface.co
if not defined HTTPS_PROXY set "HTTPS_PROXY=http://127.0.0.1:7897"
if not defined HTTP_PROXY set "HTTP_PROXY=http://127.0.0.1:7897"
cd /d "%~dp0"

rem ---- 找 Python：仓库内 .venv -> 用户级 venv -> py 启动器（不写死任何绝对路径）----
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%USERPROFILE%\xiao72-venv\Scripts\python.exe"
if not exist "%PY%" set "PY="
if not defined PY (where py >nul 2>&1 && set "PY=py")
if not defined PY goto :nopy

"%PY%" voice\run_voice.py %*
pause
exit /b 0

:nopy
echo [ERROR] 找不到 Python。
echo   1. 装 Python 3.10+（记得勾 "Add to PATH"）
echo   2. 或在项目根 .env 里写一行  X72_PYTHON=解释器完整路径
pause
exit /b 1
