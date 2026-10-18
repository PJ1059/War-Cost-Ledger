@echo off
set "HD2_PROBE_PYTHON=%USERPROFILE%\Python312\pythonw.exe"
if not exist "%HD2_PROBE_PYTHON%" (
    echo Python312 is missing: %HD2_PROBE_PYTHON%
    pause
    exit /b 1
)
start "" "%HD2_PROBE_PYTHON%" -B "%~dp0tools\probe-launcher.pyw"
