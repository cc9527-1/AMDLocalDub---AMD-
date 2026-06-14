@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   AMDLocalDub - AMD Offline Video Dubbing
echo   AMD离线配音 - 纯本地运行 / AMD GPU 加速
echo ============================================
echo.

:: Add tools to PATH (jerryshell whisper.cpp Vulkan binary + ffmpeg)
set "PATH=%CD%\whisper_jerry_bin;%PATH%"
set "PATH=%USERPROFILE%\AppData\Local\ffmpeg\ffmpeg-8.0.1-essentials_build\bin;%PATH%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

set "PY=C:\Users\73735\.workbuddy\binaries\python\versions\3.14.3\python.exe"

:: Install deps (quiet, fast if already installed)
"%PY%" -m pip install -r requirements.txt -q

:: Launch
start http://127.0.0.1:7860
echo Starting AMDLocalDub...
"%PY%" app.py

echo.
echo App closed.
pause
