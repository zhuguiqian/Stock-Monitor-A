@echo off
cd /d "%~dp0"
set "PYTHONW=%~dp0.conda_env\pythonw.exe"
if not exist "%PYTHONW%" set "PYTHONW=pythonw"
start "" "%PYTHONW%" "%~dp0stock_monitor.py"
exit
