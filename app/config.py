from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
WORKSPACE_DIR = ROOT / "workspace"
ENV_PATH = ROOT / ".env"

load_dotenv(ENV_PATH)


def _clean(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


def _gh_logged_in() -> bool:
    if _clean(os.getenv("GH_TOKEN")) or _clean(os.getenv("GITHUB_TOKEN")):
        return True
    try:
        import shutil
        import subprocess

        gh = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"
        if not gh:
            return False
        subprocess.check_output([gh, "auth", "token"], timeout=5, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


VAULT_DIR = Path(_clean(os.getenv("OBSIDIAN_VAULT")) or str(ROOT / "vault"))
DATA_DIR.mkdir(exist_ok=True)
WORKSPACE_DIR.mkdir(exist_ok=True)
VAULT_DIR.mkdir(exist_ok=True)


XAI_API_KEY = _clean(os.getenv("XAI_API_KEY"))
GITHUB_TOKEN = _clean(os.getenv("GITHUB_TOKEN"))
GITHUB_USERNAME = _clean(os.getenv("GITHUB_USERNAME")) or "rkenagy-ops"
OWNER_NAME = _clean(os.getenv("JARVIS_OWNER_NAME")) or "Rhett"
VOICE = _clean(os.getenv("JARVIS_VOICE")) or "orion"
MODEL = _clean(os.getenv("JARVIS_MODEL")) or "grok-4.6"
HOST = _clean(os.getenv("JARVIS_HOST")) or "127.0.0.1"
PORT = int(_clean(os.getenv("JARVIS_PORT")) or "8787")
TRADING_MODE = (_clean(os.getenv("TRADING_MODE")) or "paper").lower()
TRADING_REQUIRE_CONFIRMATION = (_clean(os.getenv("TRADING_REQUIRE_CONFIRMATION")) or "true").lower() == "true"
PAPER_CASH = float(_clean(os.getenv("PAPER_CASH")) or "100000")
WATCHLIST = [s.strip().upper() for s in (_clean(os.getenv("JARVIS_WATCHLIST")) or "SPY,QQQ,AAPL,MSFT,NVDA,TSLA,BTC-USD").split(",") if s.strip()]
AUTONOMY_ENABLED = (_clean(os.getenv("JARVIS_AUTONOMY")) or "true").lower() == "true"
OBSIDIAN_API_URL = _clean(os.getenv("OBSIDIAN_API_URL"))
OBSIDIAN_API_KEY = _clean(os.getenv("OBSIDIAN_API_KEY"))
N8N_WEBHOOK_URL = _clean(os.getenv("N8N_WEBHOOK_URL"))
JELLYFIN_URL = _clean(os.getenv("JELLYFIN_URL"))
JELLYFIN_API_KEY = _clean(os.getenv("JELLYFIN_API_KEY"))
IMMICH_URL = _clean(os.getenv("IMMICH_URL"))
IMMICH_API_KEY = _clean(os.getenv("IMMICH_API_KEY"))
POSTIZ_URL = _clean(os.getenv("POSTIZ_URL"))
STIRLING_URL = _clean(os.getenv("STIRLING_URL"))
WORDPRESS_URL = _clean(os.getenv("WORDPRESS_URL"))
WORDPRESS_USER = _clean(os.getenv("WORDPRESS_USER"))
WORDPRESS_APP_PASSWORD = _clean(os.getenv("WORDPRESS_APP_PASSWORD"))
X_BEARER_TOKEN = _clean(os.getenv("X_BEARER_TOKEN"))
AMAZON_MARKETPLACE = _clean(os.getenv("AMAZON_MARKETPLACE")) or "US"

XAI_BASE = "https://api.x.ai/v1"
XAI_REALTIME = "wss://api.x.ai/v1/realtime"
GITHUB_API = "https://api.github.com"
DB_PATH = DATA_DIR / "jarvis.db"


def reload_env() -> None:
    load_dotenv(ENV_PATH, override=True)
    global XAI_API_KEY, GITHUB_TOKEN, GITHUB_USERNAME, OWNER_NAME, VOICE, MODEL, TRADING_MODE, AUTONOMY_ENABLED
    global WORDPRESS_URL, WORDPRESS_USER, WORDPRESS_APP_PASSWORD, X_BEARER_TOKEN, POSTIZ_URL
    XAI_API_KEY = _clean(os.getenv("XAI_API_KEY"))
    GITHUB_TOKEN = _clean(os.getenv("GITHUB_TOKEN"))
    GITHUB_USERNAME = _clean(os.getenv("GITHUB_USERNAME")) or "rkenagy-ops"
    OWNER_NAME = _clean(os.getenv("JARVIS_OWNER_NAME")) or "Rhett"
    VOICE = _clean(os.getenv("JARVIS_VOICE")) or "orion"
    MODEL = _clean(os.getenv("JARVIS_MODEL")) or "grok-4.6"
    TRADING_MODE = (_clean(os.getenv("TRADING_MODE")) or "paper").lower()
    AUTONOMY_ENABLED = (_clean(os.getenv("JARVIS_AUTONOMY")) or "true").lower() == "true"
    WORDPRESS_URL = _clean(os.getenv("WORDPRESS_URL"))
    WORDPRESS_USER = _clean(os.getenv("WORDPRESS_USER"))
    WORDPRESS_APP_PASSWORD = _clean(os.getenv("WORDPRESS_APP_PASSWORD"))
    X_BEARER_TOKEN = _clean(os.getenv("X_BEARER_TOKEN"))
    POSTIZ_URL = _clean(os.getenv("POSTIZ_URL"))


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
        "github_configured": bool(GITHUB_TOKEN) or _gh_logged_in(),
        "github_username": GITHUB_USERNAME or None,
        "owner": OWNER_NAME,
        "voice": VOICE,
        "model": MODEL,
        "online": True,
        "trading_mode": TRADING_MODE,
        "autonomy": AUTONOMY_ENABLED,
        "watchlist": WATCHLIST,
        "workspace": str(WORKSPACE_DIR),
        "vault": str(VAULT_DIR),
        "obsidian_api": bool(OBSIDIAN_API_URL),
        "n8n": bool(N8N_WEBHOOK_URL),
        "brain": "grok" if XAI_API_KEY else "free",
    }
