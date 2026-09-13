@echo off
setlocal EnableExtensions EnableDelayedExpansion
title BOOM AI KONKOOR MENTOR
cd /d "%~dp0"
set "ROOT=%~dp0"
if not exist "%ROOT%backend" if exist "%ROOT%Boom-merged\backend" set "ROOT=%ROOT%Boom-merged\"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "VENV=%BACKEND%\.venv"
set "LLM_MODEL=aya-expanse:8b-q4_K_S"
set "EMBED_MODEL=nomic-embed-text"
set "OLLAMA_URL=http://127.0.0.1:11434"

echo ================================================================
echo             BOOM AI KONKOOR MENTOR
echo       Setup + RAG + Ollama + Frontend
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

REM ----- Ollama -----
where ollama >nul 2>&1
if errorlevel 1 (
  echo [INFO] Ollama not found. Attempting install with winget...
  where winget >nul 2>&1 || (echo [ERROR] winget not available. Install Ollama manually from https://ollama.com/download/windows&pause&exit /b 1)
  winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (echo [ERROR] Ollama installation failed.&pause&exit /b 1)
  set "PATH=%PATH%;%LocalAppData%\Programs\Ollama;%ProgramFiles%\Ollama"
)
where ollama >nul 2>&1 || (echo [ERROR] Ollama not available in this window. Close and reopen the terminal.&pause&exit /b 1)
echo [OK] Ollama found

REM ----- Python virtual environment -----
if not exist "%VENV%\Scripts\python.exe" (
  echo [SETUP] Creating virtual environment...
  %PYEXE% -m venv "%VENV%"
  if errorlevel 1 (echo [ERROR] Failed to create virtual environment.&pause&exit /b 1)
)
set "VPY=%VENV%\Scripts\python.exe"
if not exist "%VPY%" (echo [ERROR] Virtual environment Python missing.&pause&exit /b 1)
echo [OK] Virtual environment ready

REM ----- Install Python dependencies -----
echo [SETUP] Upgrading pip...
"%VPY%" -m pip install --upgrade pip --quiet
if exist "%BACKEND%\requirements.txt" (
  echo [SETUP] Installing backend dependencies...
  "%VPY%" -m pip install -r "%BACKEND%\requirements.txt" --quiet
  if errorlevel 1 (
    echo [ERROR] Backend dependencies failed.
    echo        Try deleting %VENV% and running this script again.
    pause&exit /b 1
  )
)
echo [OK] Backend dependencies installed

REM ----- Backend .env -----
if not exist "%BACKEND%\.env" (
  if exist "%BACKEND%\.env.example" (
    echo [SETUP] Creating .env from .env.example...
    copy /Y "%BACKEND%\.env.example" "%BACKEND%\.env" >nul
  ) else (
    echo [WARNING] No .env or .env.example found in backend folder.
  )
)

REM ----- Frontend dependencies -----
echo [SETUP] Installing frontend dependencies...
cd /d "%FRONTEND%"
if exist package-lock.json (call npm ci --silent) else (call npm install --silent)
if errorlevel 1 (echo [ERROR] Frontend dependencies failed.&pause&exit /b 1)
cd /d "%ROOT%"
echo [OK] Frontend dependencies installed

REM ----- Start Ollama and wait for API -----
echo [SETUP] Starting Ollama...
curl.exe -s "%OLLAMA_URL%/api/tags" >nul 2>&1
if errorlevel 1 (
  start "Ollama" /min cmd /c "ollama serve"
  echo        Waiting for Ollama API...
)
set /a tries=0
:waitollama
curl.exe -s "%OLLAMA_URL%/api/tags" >nul 2>&1
if not errorlevel 1 goto ollamaready
set /a tries+=1
if !tries! GEQ 30 (echo [ERROR] Ollama did not become ready after 60 seconds.&pause&exit /b 1)
timeout /t 2 /nobreak >nul
goto waitollama
:ollamaready
echo [OK] Ollama API ready

REM ----- Pull models -----
echo [SETUP] Pulling LLM model: %LLM_MODEL%
ollama pull "%LLM_MODEL%"
if errorlevel 1 (
  echo [WARNING] Q4 model unavailable, trying aya-expanse:8b...
  set "LLM_MODEL=aya-expanse:8b"
  ollama pull "!LLM_MODEL!"
  if errorlevel 1 (echo [ERROR] Could not pull Aya Expanse model.&pause&exit /b 1)
)
echo [OK] LLM model ready: %LLM_MODEL%

echo [SETUP] Pulling embedding model: %EMBED_MODEL%
ollama pull "%EMBED_MODEL%"
if errorlevel 1 (echo [ERROR] Could not pull embedding model.&pause&exit /b 1)
echo [OK] Embedding model ready: %EMBED_MODEL%

REM ----- Pre-ingest raw PDFs picture-by-picture -----
echo [SETUP] Embedding raw PDFs (backend\data\raw) page-by-page...
echo        First run may take a while (big scanned books). Later runs are fast.
cd /d "%BACKEND%"
"%VPY%" -m app.rag.ingest_raw
if errorlevel 1 (echo [WARNING] Raw PDF ingestion step failed, continuing anyway.)
cd /d "%ROOT%"
echo [OK] Raw PDF ingestion step finished

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
echo   Ollama:   %OLLAMA_URL%
echo ================================================================
echo.
echo Close this window to stop. Backend and Frontend run in separate windows.
pause
