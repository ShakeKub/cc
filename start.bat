@echo off
setlocal

:: Re-launch as Administrator if not already elevated (UAC)
whoami /groups | find "S-1-16-12288" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Requesting Administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    if %errorlevel% neq 0 (
        echo.
        echo [!] Administrator privileges are required. UAC request was canceled.
        pause
    )
    exit /b
)

:: Move to the folder where this .bat lives so relative paths work
cd /d "%~dp0"

:: Run the app (prefer local virtual environment first)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "%~dp0main.py"
) else (
    py -3 "%~dp0main.py" 2>nul || python "%~dp0main.py"
)

if %errorlevel% neq 0 (
    echo.
    echo [!] Python not found or main.py failed.
    echo     Make sure Python 3.10+ is installed and available in PATH.
    pause
)

endlocal
