@echo off
setlocal EnableExtensions EnableDelayedExpansion
title BOOM AI KONKOOR MENTOR
cd /d "%~dp0"
set "ROOT=%~dp0"
set "ROOT=%~dp0"
if not exist "%ROOT%backend" if exist "%ROOT%Boom-merged\backend" set "ROOT=%ROOT%Boom-merged\"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "VENV=%BACKEND%\.venv"
set "LLM_MODEL=aya-expanse:8b-q4_K_S"
set "EMBED_MODEL=nomic-embed-text"

echo ================================================================
echo             BOOM AI KONKOOR MENTOR
echo       Setup + RAG + Frontend
echo ================================================================
echo.

if not exist "%BACKEND%" (echo [ERROR] backend folder not found.&pause&exit /b 1)
if not exist "%FRONTEND%" (echo [ERROR] frontend folder not found.&pause&exit /b 1)

REM ----- Find Python (prefer 3.12, accept 3.11-3.13) -----
set "PYEXE="

REM Try py launcher for 3.12 first, then 3.13, then 3.11
where py >nul 2>&1
if not errorlevel 1 (
  for %%V in (3.12 3.13 3.11) do (
    if not defined PYEXE (
      py -%%V -c "import sys; raise SystemExit(0 if sys.version_info[:2]>=(3,11) else 1)" >nul 2>&1 && set "PYEXE=py -%%V"
    )
  )
)

REM Try well-known install paths
if not defined PYEXE (
  for %%V in (312 313 311) do (
    if not defined PYEXE (
      if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python%%V\python.exe"
    )
  )
)
if not defined PYEXE (
  for %%V in (312 313 311) do (
    if not defined PYEXE (
      if exist "%ProgramFiles%\Python%%V\python.exe" set "PYEXE=%ProgramFiles%\Python%%V\python.exe"
    )
  )
)

REM Fallback: any python on PATH that is 3.11+
if not defined PYEXE (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined PYEXE (
      "%%P" -c "import sys; raise SystemExit(0 if sys.version_info[:2]>=(3,11) and sys.version_info[:2]<=(3,13) else 1)" >nul 2>&1 && set "PYEXE=%%P"
    )
  )
)

if not defined PYEXE (
  echo [ERROR] Python 3.11-3.13 was not found.
  echo        Run "py -0p" to check installed versions.
  echo        Download from https://www.python.org/downloads/
  pause&exit /b 1
)
echo [OK] Using Python:
%PYEXE% --version

REM ----- Node.js -----
where node >nul 2>&1
if errorlevel 1 (
  echo [INFO] Node.js not found. Attempting install with winget...
  where winget >nul 2>&1 || (echo [ERROR] winget not available. Install Node.js LTS manually from https://nodejs.org&pause&exit /b 1)
  winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (echo [ERROR] Node.js installation failed.&pause&exit /b 1)
  set "PATH=%PATH%;%ProgramFiles%\nodejs;%LocalAppData%\Programs\nodejs"
)
node --version >nul 2>&1 || (echo [ERROR] Node.js is unavailable in this window. Close and reopen the terminal.&pause&exit /b 1)
echo [OK] Node.js found
node --version

REM ----- Start backend -----
echo.
echo [START] Backend: http://127.0.0.1:8000
start "Boom Backend" cmd /k "cd /d "%BACKEND%" && "%VPY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
timeout /t 4 /nobreak >nul

REM ----- Start frontend -----
echo [START] Frontend: http://127.0.0.1:8443
start "Boom Frontend" cmd /k "cd /d "%FRONTEND%" && npm run dev"
timeout /t 5 /nobreak >nul

REM ----- Open browser -----
start "" http://127.0.0.1:8443

echo.
echo ================================================================
echo   BOOM IS RUNNING
echo   Frontend: http://127.0.0.1:8443
echo   Backend:  http://127.0.0.1:8000
echo ================================================================
echo.
echo Close this window to stop. Backend and Frontend run in separate windows.
pause