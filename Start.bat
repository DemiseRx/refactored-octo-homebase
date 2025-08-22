@echo off
setlocal ENABLEDELAYEDEXPANSION

REM ==== Configuration ====
set "PROJ=C:\Users\thill\Desktop\Project"
set "VENV=%PROJ%\env"
set "PYEXE=%VENV%\Scripts\python.exe"
set "PIP=%VENV%\Scripts\pip.exe"
set "MAIN=%PROJ%\audiobook_generator.py"


REM ==== Move to project ====
cd /d "%PROJ%" || (
  echo [ERROR] Project folder not found: "%PROJ%"
  pause & exit /b 1
)

REM ==== Ensure venv exists ====
if not exist "%PYEXE%" (
  echo [INFO] Creating virtual environment...
  python -m venv "%VENV%" || (
    echo [ERROR] Could not create venv at "%VENV%".
    echo Make sure Python 3.8+ is installed and on PATH.
    pause & exit /b 1
  )
)

REM ==== Upgrade pip tooling (quiet) ====
"%PYEXE%" -m pip install --upgrade pip setuptools wheel >nul 2>&1

REM ==== Ensure core project deps ====
echo [INFO] Verifying core dependencies...
"%PYEXE%" - <<PYCHECK >nul 2>&1
import sys
missing=[]
for mod in ("PySide6","requests","soundfile","docx","numpy"):
    try: __import__(mod)
    except Exception: missing.append(mod)
if missing:
    print("MISSING:"+";".join(missing))
    sys.exit(1)
PYCHECK

if errorlevel 1 (
  echo [INFO] Installing project requirements...
  "%PYEXE%" -m pip install -r "%PROJ%\requirements.txt" || (
    echo [ERROR] Failed installing core requirements. See errors above.
    pause & exit /b 1
  )
)

REM ==== Check Higgs Audio install (boson_multimodal) ====
echo [INFO] Checking Higgs Audio package...
"%PYEXE%" - <<PYCHECK >nul 2>&1
import importlib, sys
importlib.import_module("boson_multimodal")
PYCHECK

if errorlevel 1 (
  echo.
  echo [WARN] Higgs Audio (boson_multimodal) not found in this venv.
  echo        Install it before running TTS:
  echo        1) Open a new Command Prompt.
  echo        2) call "%VENV%\Scripts\activate"
  echo        3) cd C:\Users\thill\Desktop\higgs-audio   (adjust if needed)
  echo        4) python -m pip install -r requirements.txt
  echo        5) python -m pip install -e .
  echo.
  choice /C YN /M "Continue and launch GUI anyway (you can still parse chapters, but audio will fail)?"
  if errorlevel 2 ( exit /b 1 )
)

REM ==== LM Studio hint (optional) ====
echo [NOTE] Make sure LM Studio's API server is running on http://localhost:1234/v1
echo        If parsing fails to contact the model, start LM Studio > Developer > Start Server.

REM ==== Launch the GUI ====
echo [INFO] Launching Audiobook Generator...
"%PYEXE%" "%MAIN%"
set EXITCODE=%ERRORLEVEL%

if %EXITCODE% NEQ 0 (
  echo.
  echo [ERROR] Application exited with code %EXITCODE%.
  echo Review the console output above for details.
  pause
) else (
  echo.
  echo [DONE] Application closed.
  pause
)
