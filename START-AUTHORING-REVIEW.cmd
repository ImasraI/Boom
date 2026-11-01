@echo off
"%~dp0backend\.venv\Scripts\python.exe" -X utf8 "%~dp0backend\scripts\start_authoring_review.py"
if errorlevel 1 pause
