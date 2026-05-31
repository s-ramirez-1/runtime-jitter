@echo off
echo Setting up runtime-draft on Windows...

python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Setup complete. To run the project:
echo   .venv\Scripts\activate
echo   python scripts\batch_run.py
