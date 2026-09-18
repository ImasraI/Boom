@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "VENVPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENVPY%" set "VENVPY=python"

echo ============================================================
echo   Boom  -  OCR + Embed  (Google Gemini)
echo   ========================================================
echo   . Reads every scanned book under data\raw\test-books
echo   . Transcribes pages not OCR'd yet (Gemini vision)
echo   . Embeds each fully-OCR'd book into the text store
echo   . Stops when today's Gemini cap (200 images) is reached
echo   .
echo   Re-run this file DAILY until "Still pending: none".
echo ============================================================
echo.

"%VENVPY%" -m app.rag.ocr_corpus

echo.
echo ------------------------------------------------------------
echo Done with this session. If it says "Capped", run me again
echo tomorrow to continue. Books fully OCR'd were embedded.
echo ------------------------------------------------------------
pause
endlocal