@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if not defined EXAM_OCR_PROXY set "EXAM_OCR_PROXY=http://127.0.0.1:10809"
if not defined EXAM_OCR_GEMINI_MODEL set "EXAM_OCR_GEMINI_MODEL=gemini-3.8-flash"
if not defined EXAM_OCR_GROQ_OUTPUT_TOKENS set "EXAM_OCR_GROQ_OUTPUT_TOKENS=16384"
.venv\Scripts\python.exe -X utf8 scripts/import_exam_examples.py scan --provider auto --workers 8 --limit 7 --watch --live
echo.
echo Scan stopped. Saved page/question checkpoints are preserved.
echo Run START-EXAM-WORKERS.cmd from the project root to resume later.
