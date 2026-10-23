@echo off
chcp 65001 >nul 2>&1
title XIAO72 LED CONTROL
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"
"C:\Users\ROG\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" launcher.py %*
