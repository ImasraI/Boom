@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "VENVPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VENVPY%" set "VENVPY=python"

echo ============================================================
echo   Boom  -  OCR + Embed  (incremental; safe to re-run anytime)
echo ============================================================
echo   1. OCR any not-yet-OCR'd pages  (Gemini vision)
echo      - Resumes exactly where it stopped; never re-OCR's
echo        finished pages; never re-embeds finished books.
echo   2. Embed fully-OCR'd books into the TEXT store (Ollama).
echo   3. Embed raw PDFs as page images into the IMAGE store.
echo   4. Stops at today's Gemini cap (200 images).
echo.
echo   Safe to run after a break / Ctrl+C / crash:
echo     - No previous work is deleted or overwritten.
echo     - Only new books / remaining pages / remaining images run.
echo   Re-run daily until:
echo     - OCR says "Still pending: none"
echo     - Ingest reports all PDFs skipped (already embedded)
echo ============================================================
echo.

echo --- Step 1/3: OCR raw books + embed OCR text (resumes) ---
"%VENVPY%" -m app.rag.ocr_corpus
if errorlevel 1 (
    echo [ocr_corpus exited with error - see log above]
)

echo.
echo --- Step 2/3: Embed raw PDFs as page images (skips done) ---
"%VENVPY%" -m app.rag.ingest_raw
if errorlevel 1 (
    echo [ingest_raw exited with error - see log above]
)

echo.
echo ------------------------------------------------------------
echo Done for today. Next run continues exactly where this left off.
echo ------------------------------------------------------------
pause
endlocal
