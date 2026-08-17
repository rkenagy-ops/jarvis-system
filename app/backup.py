"""Zip vault + SQLite mind. Never pack .env or tokens."""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import config

SKIP = {".env", ".env.local", "room.json"}


def dest_dir() -> Path:
    d = config.WORKSPACE_DIR / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run() -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = dest_dir() / f"jarvis-{stamp}.zip"
    count = 0
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        vault = Path(config.VAULT_DIR)
        if vault.exists():
            for f in vault.rglob("*"):
                if f.is_file() and ".obsidian" not in f.parts and f.name not in SKIP:
                    zf.write(f, f"vault/{f.relative_to(vault).as_posix()}")
                    count += 1
        db = Path(config.DB_PATH)
        if db.exists():
            zf.write(db, "data/jarvis.db")
            count += 1
    return {"ok": True, "path": str(path), "files": count, "bytes": path.stat().st_size}


def latest() -> dict | None:
    zips = sorted(dest_dir().glob("jarvis-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not zips:
        return None
    p = zips[0]
    return {"path": str(p), "bytes": p.stat().st_size, "mtime": p.stat().st_mtime}
