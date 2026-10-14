@echo off
chcp 65001 >nul
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
  echo Backend Python environment is missing. Run backend setup first.
  pause
  exit /b 1
)
rem Local pilot only. This is separate from the old book-OCR workers.
rem Preserve an explicit proxy override; the laptop's working VPN listens here.
if not defined EXAM_OCR_PROXY set "EXAM_OCR_PROXY=http://127.0.0.1:10809"
.venv\Scripts\python.exe -X utf8 scripts/exam_scan_status.py --is-running >nul
if errorlevel 1 (
  start "Exam OCR - visible scanner" /D "%~dp0backend" cmd /k scripts\run_exam_scan.cmd
) else (
  echo The scanner is already running; reusing it.
)
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if errorlevel 1 start "Exam OCR - live monitor" /D "%~dp0backend" cmd /k .venv\Scripts\python.exe -X utf8 scripts/exam_scan_status.py --serve --port 8770
echo Scanner and monitor opened. Progress: http://127.0.0.1:8770/
echo Run this file again after waking the laptop to resume saved checkpoints.
