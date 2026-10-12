@echo off
cd /d "%~dp0"
python fm_live.py --image fm_lecture_debug.png > diag_out.txt 2>&1
python fm_live.py
pause
