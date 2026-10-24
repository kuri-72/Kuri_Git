@echo off
chcp 65001 >nul 2>&1
title XIAO72 VOICE ASSISTANT
rem ============================================================
rem  Xiao72 voice assistant - one click launcher
rem  No absolute paths: finds any venv automatically,
rem  model dir comes from .env / X72_MODEL_DIR.
rem ============================================================
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set HF_HUB_DISABLE_XET=1
set HF_ENDPOINT=https://huggingface.co
rem NOTE: HTTPS_PROXY is intentionally NOT set here.
rem   Models are already downloaded, so no proxy is needed at runtime.
rem   Setting it would break DeepSeek calls whenever Clash is off.
rem   To re-download models: open Clash, then run
rem     set HTTPS_PROXY=http://127.0.0.1:7897
cd /d "%~dp0"

rem ---- find python: repo/.venv -> ~/xiao72-venv -> py launcher ----
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%USERPROFILE%\xiao72-venv\Scripts\python.exe"
if not exist "%PY%" set "PY="
if not defined PY (where py >nul 2>&1 && set "PY=py")
if not defined PY goto :nopy

"%PY%" voice\run_voice.py %*
echo.
echo ============================================================
echo  Exited. Press any key to close this window.
pause >nul
exit /b 0

:nopy
echo [ERROR] Python not found.
echo   1. Install Python 3.10+ (check "Add to PATH")
echo   2. Or set X72_PYTHON=<full path> in .env
pause
exit /b 1
