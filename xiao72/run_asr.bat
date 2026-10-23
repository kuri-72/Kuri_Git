@echo off
chcp 65001 >nul 2>&1
title XIAO72 ASR
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set HF_HUB_DISABLE_XET=1
set HF_ENDPOINT=https://huggingface.co
set HTTPS_PROXY=http://127.0.0.1:7897
set HTTP_PROXY=http://127.0.0.1:7897
set X72_MODEL_DIR=D:\AI_Cache\models
cd /d "%~dp0"
if not exist "E:\xiao72-venv\Scripts\python.exe" (
  echo [ERROR] venv not found: E:\xiao72-venv
  pause
  exit /b 1
)
"E:\xiao72-venv\Scripts\python.exe" voice\check_asr.py %*
pause
