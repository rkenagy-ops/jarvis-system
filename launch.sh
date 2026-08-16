#!/usr/bin/env bash
set -e

if [ ! -f .env ]; then
  echo "No .env found. Copy .env.example to .env and fill in your keys first."
  exit 1
fi

echo "Starting support services (litellm, n8n, whisper, piper)..."
docker compose up -d

echo "Installing python dependencies..."
pip install -r requirements.txt

echo "Starting the Jarvis orchestrator..."
python orchestrator.py
