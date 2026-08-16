@echo off
cd /d "%~dp0"
if not exist .env copy .env.example .env >nul
echo Starting Super Jarvis HUD...
powershell -ExecutionPolicy Bypass -File "%~dp0start.ps1"
