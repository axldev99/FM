@echo off
cd /d "%~dp0"
python activer_clics.py
if errorlevel 1 (
    pause
    exit /b 1
)
python fm_avec_clics.py %*
pause
