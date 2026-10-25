@echo off
setlocal
cd /d "%~dp0"
rem Choisir Python 3.13 64 bits, meme si "python" pointe vers une autre version.
set "FM_PYTHON="
py -3.13 -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,13) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
if not errorlevel 1 set "FM_PYTHON=py -3.13"
if not defined FM_PYTHON (
    python -c "import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,13) and struct.calcsize('P') == 8 else 1)" >nul 2>&1
    if not errorlevel 1 set "FM_PYTHON=python"
)
if not defined FM_PYTHON (
    echo Python 3.13 64 bits est requis pour ce projet.
    echo Installe cette version puis ferme et relance ce fichier.
    echo https://www.python.org/downloads/windows/
    pause
    exit /b 1
)
%FM_PYTHON% activer_clics.py assistant_sans_clic.py
if errorlevel 1 (
    pause
    exit /b 1
)
%FM_PYTHON% fm_avec_clics.py %*
pause
