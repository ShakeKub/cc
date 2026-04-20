@echo off
:: Re-launch as Administrator if not already elevated
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: Move to the folder where this .bat lives so relative paths work
cd /d "%~dp0"

:: Run the app
python main.py
if %errorlevel% neq 0 (
    echo.
    echo  [!] Python not found or main.py failed.
    echo      Make sure Python 3.10+ is installed and added to PATH.
    pause
)
