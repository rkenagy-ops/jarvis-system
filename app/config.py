from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
ENV_PATH = ROOT / ".env"

load_dotenv(ENV_PATH)

DATA_DIR.mkdir(exist_ok=True)


def _clean(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


XAI_API_KEY = _clean(os.getenv("XAI_API_KEY"))
GITHUB_TOKEN = _clean(os.getenv("GITHUB_TOKEN"))
GITHUB_USERNAME = _clean(os.getenv("GITHUB_USERNAME")) or "rkenagy-ops"
OWNER_NAME = _clean(os.getenv("JARVIS_OWNER_NAME")) or "Rhett"
VOICE = _clean(os.getenv("JARVIS_VOICE")) or "orion"
MODEL = _clean(os.getenv("JARVIS_MODEL")) or "grok-4.6"
HOST = _clean(os.getenv("JARVIS_HOST")) or "127.0.0.1"
PORT = int(_clean(os.getenv("JARVIS_PORT")) or "8787")

XAI_BASE = "https://api.x.ai/v1"
XAI_REALTIME = "wss://api.x.ai/v1/realtime"
GITHUB_API = "https://api.github.com"
DB_PATH = DATA_DIR / "jarvis.db"


def reload_env() -> None:
    load_dotenv(ENV_PATH, override=True)
    global XAI_API_KEY, GITHUB_TOKEN, GITHUB_USERNAME, OWNER_NAME, VOICE, MODEL
    XAI_API_KEY = _clean(os.getenv("XAI_API_KEY"))
    GITHUB_TOKEN = _clean(os.getenv("GITHUB_TOKEN"))
    GITHUB_USERNAME = _clean(os.getenv("GITHUB_USERNAME")) or "rkenagy-ops"
    OWNER_NAME = _clean(os.getenv("JARVIS_OWNER_NAME")) or "Rhett"
    VOICE = _clean(os.getenv("JARVIS_VOICE")) or "orion"
    MODEL = _clean(os.getenv("JARVIS_MODEL")) or "grok-4.6"


def save_env(updates: dict[str, str]) -> None:
    existing: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            existing[key.strip()] = value
    for key, value in updates.items():
        if value is None:
            continue
        existing[key] = str(value)
        os.environ[key] = str(value)
    lines = [f"{k}={v}" for k, v in existing.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    reload_env()


def status() -> dict:
    return {
        "xai_configured": bool(XAI_API_KEY),
        "github_configured": bool(GITHUB_TOKEN),
        "github_username": GITHUB_USERNAME or None,
        "owner": OWNER_NAME,
        "voice": VOICE,
        "model": MODEL,
        "online": True,
    }
