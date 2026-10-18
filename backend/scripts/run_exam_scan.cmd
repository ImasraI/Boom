@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if not defined EXAM_OCR_PROXY set "EXAM_OCR_PROXY=http://127.0.0.1:10809"
if not defined EXAM_OCR_GEMINI_MODEL set "EXAM_OCR_GEMINI_MODEL=gemini-3.5-flash-lite"
if not defined EXAM_OCR_GEMINI_THINKING set "EXAM_OCR_GEMINI_THINKING=minimal"
if not defined EXAM_OCR_GEMINI_OUTPUT_TOKENS set "EXAM_OCR_GEMINI_OUTPUT_TOKENS=8192"
if not defined EXAM_OCR_ANNOTATION_REASONING set "EXAM_OCR_ANNOTATION_REASONING=none"
if not defined EXAM_OCR_GROQ_OUTPUT_TOKENS set "EXAM_OCR_GROQ_OUTPUT_TOKENS=1000"
if not defined EXAM_OCR_GROQ_REASONING set "EXAM_OCR_GROQ_REASONING=none"
if not defined EXAM_OCR_WORKERS set "EXAM_OCR_WORKERS=30"
if not defined EXAM_OCR_PAGE_LIMIT set "EXAM_OCR_PAGE_LIMIT=30"
set "EXAM_OCR_BATCH_ARGS="
if "%EXAM_OCR_NEXT_BATCH%"=="1" set "EXAM_OCR_BATCH_ARGS=--next-batch"
powershell -NoProfile -Command "& .venv\Scripts\python.exe -X utf8 scripts/import_exam_examples.py scan --provider gemini --method whole-page --workers %EXAM_OCR_WORKERS% --limit %EXAM_OCR_PAGE_LIMIT% %EXAM_OCR_BATCH_ARGS% --watch --live --auto-next 2>&1 | Tee-Object -FilePath data/exam_examples/scanner-console.log; exit $LASTEXITCODE"
echo.
echo Scan stopped. Saved page/question checkpoints are preserved.
echo To resume later, run "%~dp0..\..\START-EXAM-WORKERS.cmd"
echo To select the next completed evaluation batch, add next after that command.
