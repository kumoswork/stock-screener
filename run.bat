@echo off
cd /d %~dp0
if not exist .venv (
  echo Creating virtual environment...
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
echo.
echo Starting screener at http://localhost:8501
streamlit run app.py
pause
