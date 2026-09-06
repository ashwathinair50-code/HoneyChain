@echo off
title HoneyChain / BeeTrust AI - SIH Hackathon Server
echo ===================================================
echo   BeeTrust AI / HoneyChain - SIH 2026 Edition
echo ===================================================
echo.

REM Check Python availability
python --version >nul 2>&1
if %errorlevel% neq 0 (
    if exist .venv\Scripts\python.exe (
        set PYTHON_EXE=.venv\Scripts\python.exe
    ) else (
        echo [ERROR] Python is not installed or not in your PATH.
        echo Please install Python 3.12+ and add it to PATH.
        pause
        exit /b 1
    )
) else (
    set PYTHON_EXE=python
)

echo Initializing synthetic demo database and batches...
%PYTHON_EXE% -m backend.demo_setup

echo.
echo ===================================================
echo   Server is running at: http://127.0.0.1:8000
echo   Open your browser to http://127.0.0.1:8000
echo ===================================================
echo.

%PYTHON_EXE% -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8000
pause
