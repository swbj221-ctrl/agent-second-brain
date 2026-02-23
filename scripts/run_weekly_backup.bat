@echo off
setlocal

set "PROJECT_ROOT=D:\openclaw_bot\agent-second-brain"
set "PYTHONPATH=%PROJECT_ROOT%\src"
set "PYTHON_EXE=%PROJECT_ROOT%\venv\Scripts\python.exe"
set "LOG_DIR=%PROJECT_ROOT%\logs"
set "LOG_FILE=%LOG_DIR%\backup_weekly.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

"%PYTHON_EXE%" "%PROJECT_ROOT%\scripts\db_backup_job.py" --run >> "%LOG_FILE%" 2>&1
exit /b %ERRORLEVEL%
