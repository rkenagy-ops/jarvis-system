"""What 'finished' means for Super Jarvis 5.0 — status only, no secrets."""

from __future__ import annotations

from pathlib import Path

from . import backup, config, ollama as ollama_mod, xai, xpost


def checklist() -> dict:
    grok = bool(xai.probe().get("ok")) if config.XAI_API_KEY else False
    ol = ollama_mod.probe()
    wp = bool(config.WORDPRESS_URL and config.WORDPRESS_USER and config.WORDPRESS_APP_PASSWORD)
    x_ready = xpost.ready()
    daily = Path(config.VAULT_DIR) / "Daily"
    has_brief = False
    if daily.exists():
        has_brief = any("briefing" in p.name.lower() or "Morning briefing" in p.read_text(encoding="utf-8", errors="replace") for p in daily.glob("*.md"))
    ev = list((Path(config.VAULT_DIR) / "Memory").glob("*-briefing-eval.md")) if (Path(config.VAULT_DIR) / "Memory").exists() else []
    items = [
        {"id": "grok", "ok": grok, "label": "Grok online"},
        {"id": "ollama", "ok": bool(ol.get("ok")), "label": f"Ollama {ol.get('model') or config.OLLAMA_MODEL}"},
        {"id": "fortress", "ok": True, "label": "Fortress loopback"},
        {"id": "vault", "ok": Path(config.VAULT_DIR).exists(), "label": "Obsidian vault"},
        {"id": "briefing", "ok": has_brief, "label": "At least one briefing on disk"},
        {"id": "wordpress", "ok": wp, "label": "WordPress live channel (recommended)"},
        {"id": "x", "ok": x_ready, "label": "X OAuth user tokens (optional)"},
        {"id": "alpaca", "ok": bool(config.ALPACA_KEY_ID and config.ALPACA_SECRET_KEY), "label": "Alpaca keys (optional paper/live)"},
        {"id": "eval", "ok": bool(ev), "label": "Briefing eval written"},
        {"id": "backup", "ok": bool(backup.latest()), "label": "At least one vault+db zip"},
    ]
    done = sum(1 for i in items if i["ok"])
    return {
        "version": "5.0",
        "done": done,
        "total": len(items),
        "complete": done >= 6,
        "recommended": "wordpress",
        "items": items,
        "next": _next(items),
    }


def _next(items: list[dict]) -> str:
    for i in items:
        if not i["ok"] and i["id"] in {"wordpress", "backup", "eval"}:
            return i["label"]
    return "Use it. Keys you do not have stay optional."
