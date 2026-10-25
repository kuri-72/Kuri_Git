@echo off
chcp 65001 >nul 2>&1
title XIAO72 UI
rem ============================================================
rem  Xiao72 monitor window. No absolute paths.
rem  Interpreter comes from .env (X72_PYTHON) or local venvs.
rem ============================================================
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"

if exist "%~dp0.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%~dp0.env") do (
    if /i "%%a"=="X72_PYTHON" set "X72_PYTHON=%%b"
  )
)

set "PY=%X72_PYTHON%"
if not defined PY set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%USERPROFILE%\xiao72-venv\Scripts\python.exe"
if not exist "%PY%" set "PY="
if not defined PY (where py >nul 2>&1 && set "PY=py")
if not defined PY goto :nopy

"%PY%" run_ui.py %*
exit /b 0

:nopy
echo [ERROR] Python not found. Set X72_PYTHON in .env
pause
exit /b 1
