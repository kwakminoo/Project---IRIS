@echo off
cd /d "%~dp0"
python -m iris
if errorlevel 1 pause
