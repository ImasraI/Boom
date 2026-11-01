@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
  echo Backend Python environment is missing. Run backend setup first.
  pause
  exit /b 1
)
if /i "%~1"=="stop" (
  .venv\Scripts\python.exe -X utf8 scripts\exam_worker_control.py stop
  exit /b
)
if /i "%~1"=="proxy" (
  .venv\Scripts\python.exe -X utf8 scripts\exam_worker_control.py proxy "%~2"
  exit /b
)
if /i "%~1"=="status" (
  .venv\Scripts\python.exe -X utf8 scripts\exam_scan_status.py
  exit /b
)
if /i "%~1"=="monitor" goto monitor
rem Continuous local candidate scanning in batches. Source review remains separate.
rem Preserve explicit routing; auto uses the known VPN proxy when listening.
if not defined EXAM_OCR_PROXY set "EXAM_OCR_PROXY=http://127.0.0.1:10809"
rem A worker terminal may inherit next=1 from its original launch. A plain
rem restart must resume that batch, never silently advance to another one.
set "EXAM_OCR_NEXT_BATCH="
if /i "%~1"=="next" set "EXAM_OCR_NEXT_BATCH=1"
.venv\Scripts\python.exe -X utf8 scripts/exam_scan_status.py --is-running >nul
if errorlevel 1 (
  start "Exam OCR - visible scanner" /D "%~dp0backend" cmd /k scripts\run_exam_scan.cmd
) else (
  echo The scanner is already running; reusing it.
)
:monitor
if not defined EXAM_MONITOR_PORT set "EXAM_MONITOR_PORT=8771"
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %EXAM_MONITOR_PORT% -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if errorlevel 1 start "Exam OCR - live monitor" /D "%~dp0backend" cmd /k .venv\Scripts\python.exe -X utf8 scripts/exam_scan_status.py --serve --port %EXAM_MONITOR_PORT%
echo Scanner and monitor opened. Progress: http://127.0.0.1:%EXAM_MONITOR_PORT%/
echo Run this file again after waking the laptop to resume saved checkpoints.
