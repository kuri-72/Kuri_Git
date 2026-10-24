@echo off
chcp 65001 >nul 2>&1
title XIAO72 VOICE ASSISTANT
rem ============================================================
rem  Xiao72 voice assistant - one click launcher
rem  No absolute paths. Interpreter and model dir come from .env:
rem    X72_PYTHON=<python.exe full path>   (optional)
rem    X72_MODEL_DIR=<model cache dir>      (optional)
rem  If absent, falls back to repo/.venv, ~/xiao72-venv, then py.
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

rem ---- read X72_PYTHON / X72_MODEL_DIR from .env (comments start with #) ----
if exist "%~dp0.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%~dp0.env") do (
    if /i "%%a"=="X72_PYTHON" set "X72_PYTHON=%%b"
    if /i "%%a"=="X72_MODEL_DIR" set "X72_MODEL_DIR=%%b"
  )
)

rem ---- find python: .env > repo/.venv > ~/xiao72-venv > py launcher ----
set "PY=%X72_PYTHON%"
if not defined PY set "PY=%~dp0.venv\Scripts\python.exe"
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
echo   2. Or add to .env:  X72_PYTHON=^<full path to python.exe^>
pause
exit /b 1
