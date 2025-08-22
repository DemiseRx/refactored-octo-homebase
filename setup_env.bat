@echo off
REM Navigate to the Project folder
cd /d C:\Users\thill\Desktop\Project

REM Activate the virtual environment
call env\Scripts\activate

REM Confirm Python is the venv one
echo Using Python from:
where python
python --version

REM Upgrade packaging tools inside the venv
python -m pip install --upgrade pip setuptools wheel

REM Install main project requirements
python -m pip install -r requirements.txt

REM === Install Higgs Audio V2 ===
REM Adjust the path below if you extracted Higgs Audio somewhere else
cd /d C:\Users\thill\Desktop\higgs-audio
python -m pip install -r requirements.txt
python -m pip install -e .

REM Return to Project folder
cd /d C:\Users\thill\Desktop\Project

echo.
echo === Setup complete. To run the application, type: ===
echo   call env\Scripts\activate
echo   python audiobook_generator.py
echo.
pause
