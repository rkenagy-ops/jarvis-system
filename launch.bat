@echo off
if not exist .env (
  echo No .env found. Copy .env.example to .env and fill in your keys first.
  exit /b 1
)

echo Starting support services (litellm, n8n, whisper, piper)...
docker compose up -d

echo Installing python dependencies...
pip install -r requirements.txt

echo Starting the Jarvis orchestrator...
python orchestrator.py
