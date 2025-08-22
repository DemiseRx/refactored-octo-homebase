@echo off
REM Launcher for audiobook_generator3.py
REM Navigate to the project directory
cd /d C:\Users\thill\Desktop\Project

REM Activate the virtual environment if it exists
if exist env\Scripts\activate.bat (
    call env\Scripts\activate
) else (
    echo [WARN] Virtual environment not found. Running with system Python.
)

REM Run the GUI script
python audiobook_generator3.py

REM Pause to keep the window open after execution
pause
