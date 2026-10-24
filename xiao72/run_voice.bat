@echo off
chcp 65001 >nul 2>&1
title XIAO72 VOICE ASSISTANT
rem ============================================================
rem  Xiao72 voice assistant - one click launcher
rem  Needs: E:\xiao72-venv  and  D:\AI_Cache\models
rem ============================================================
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set HF_HUB_DISABLE_XET=1
set HF_ENDPOINT=https://huggingface.co
set X72_MODEL_DIR=D:\AI_Cache\models
rem NOTE: HTTPS_PROXY is intentionally NOT set here.
rem   Models are already downloaded, so no proxy is needed at runtime.
rem   Setting it would break DeepSeek calls whenever Clash is off.
rem   To re-download models: open Clash, then run
rem     set HTTPS_PROXY=http://127.0.0.1:7897
cd /d "%~dp0"
if not exist "E:\xiao72-venv\Scripts\python.exe" (
  echo [ERROR] venv not found: E:\xiao72-venv
  pause
  exit /b 1
)
"E:\xiao72-venv\Scripts\python.exe" voice\run_voice.py %*
echo.
echo ============================================================
echo  Exited. Press any key to close this window.
pause >nul
