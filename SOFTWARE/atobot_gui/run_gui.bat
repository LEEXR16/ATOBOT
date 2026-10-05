@echo off
rem Starts the ATOBOT GUI with its own Python environment (PySide6, pyqtgraph, numpy).
rem The environment lives outside the project folder (PySide6 has very long paths).
rem First run creates it automatically (needs internet, takes a few minutes).
set "VENV=%USERPROFILE%\.venvs\atobot"
set "PY=%VENV%\Scripts\python.exe"
cd /d "%~dp0"
if not exist "%PY%" (
  echo Creating Python environment in %VENV% ...
  python -m venv "%VENV%" || goto :fail
  "%PY%" -m pip install -r requirements.txt || goto :fail
)
"%PY%" main.py
if errorlevel 1 pause
exit /b 0

:fail
echo Could not create the Python environment. Is Python 3.10+ installed and on PATH?
pause
exit /b 1
