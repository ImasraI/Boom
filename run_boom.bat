@echo off
setlocal EnableExtensions EnableDelayedExpansion
title BOOM AI KONKOOR MENTOR
cd /d "%~dp0"
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "VENV=%BACKEND%\.venv"
set "ENV_FILE=%BACKEND%\.env"
set "ENV_EXAMPLE=%BACKEND%\.env.example"

echo ================================================================
echo                 BOOM AI KONKOOR MENTOR
echo ================================================================
echo.

if not exist "%BACKEND%" (echo [ERROR] backend folder not found.&pause&exit /b 1)
if not exist "%FRONTEND%" (echo [ERROR] frontend folder not found.&pause&exit /b 1)

REM Find Python 3.11 or 3.12.
set "PYEXE="
where py >nul 2>&1
if not errorlevel 1 (
  for %%V in (3.12 3.11) do if not defined PYEXE (
    py -%%V -c "import sys; raise SystemExit(0 if sys.version_info[:2]>=(3,11) and sys.version_info[:2]<=(3,12) else 1)" >nul 2>&1 && set "PYEXE=py -%%V"
  )
)
if not defined PYEXE (
  for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYEXE (
    "%%P" -c "import sys; raise SystemExit(0 if sys.version_info[:2]>=(3,11) and sys.version_info[:2]<=(3,12) else 1)" >nul 2>&1 && set "PYEXE=%%P"
  )
)
if not defined PYEXE (
  echo [ERROR] Python 3.11 or 3.12 was not found.
  echo         Install Python from https://www.python.org/downloads/
  pause&exit /b 1
)
echo [OK] Python: %PYEXE%

REM Create and populate the virtual environment.
if not exist "%VENV%\Scripts\python.exe" (
  echo [INFO] Creating Python virtual environment...
  %PYEXE% -m venv "%VENV%" || (echo [ERROR] Failed to create venv.&pause&exit /b 1)
)
set "VPY=%VENV%\Scripts\python.exe"
echo [INFO] Installing backend dependencies...
"%VPY%" -m pip install --upgrade pip || (echo [ERROR] pip upgrade failed.&pause&exit /b 1)
"%VPY%" -m pip install -r "%BACKEND%\requirements.txt" || (echo [ERROR] Backend dependency installation failed.&pause&exit /b 1)

REM Create local configuration without overwriting existing secrets.
if not exist "%ENV_FILE%" (
  copy /Y "%ENV_EXAMPLE%" "%ENV_FILE%" >nul
  if errorlevel 1 (echo [ERROR] Could not create backend\.env.&pause&exit /b 1)
  "%VPY%" -c "import secrets; from pathlib import Path; p=Path(r'%ENV_FILE%'); s=p.read_text(encoding='utf-8'); p.write_text(s.replace('replace-with-a-random-secret-key', secrets.token_urlsafe(32)), encoding='utf-8')"
  if errorlevel 1 (echo [ERROR] Could not initialize backend\.env.&pause&exit /b 1)
  echo [INFO] Created backend\.env with a generated local SECRET_KEY.
)
findstr /B /C:"LLM_API_KEY=" "%ENV_FILE%" | findstr /E /C:"=" >nul && echo [WARN] Add LLM_API_KEY to backend\.env for real LLM responses.
findstr /B /C:"EMBEDDING_API_KEY=" "%ENV_FILE%" | findstr /E /C:"=" >nul && echo [WARN] Add EMBEDDING_API_KEY to backend\.env for remote embeddings.

REM Install frontend dependencies.
where node >nul 2>&1
if errorlevel 1 (
  echo [INFO] Node.js not found. Attempting to install Node.js LTS with winget...
  where winget >nul 2>&1 || (echo [ERROR] Install Node.js LTS from https://nodejs.org&pause&exit /b 1)
  winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (echo [ERROR] Node.js installation failed.&pause&exit /b 1)
  set "PATH=%PATH%;%ProgramFiles%\nodejs;%LocalAppData%\Programs\nodejs"
)
where npm >nul 2>&1 || (echo [ERROR] npm was not found with Node.js.&pause&exit /b 1)
echo [INFO] Installing frontend dependencies...
pushd "%FRONTEND%"
if not exist ".env" if exist ".env.example" copy /Y ".env.example" ".env" >nul
call npm install || (popd&echo [ERROR] Frontend dependency installation failed.&pause&exit /b 1)
popd

REM Start both applications.
echo.
echo [START] Backend:  http://127.0.0.1:8000
start "Boom Backend" /D "%BACKEND%" cmd /k ""%VPY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
timeout /t 4 /nobreak >nul
echo [START] Frontend: http://127.0.0.1:8443
start "Boom Frontend" /D "%FRONTEND%" cmd /k "call npm run dev"
timeout /t 5 /nobreak >nul
start "" http://127.0.0.1:8443

echo.
echo Frontend: http://127.0.0.1:8443
echo Backend:  http://127.0.0.1:8000
echo Close the two application windows to stop Boom.
pause
