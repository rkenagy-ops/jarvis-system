from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import poly


def test_kelly_positive_and_zero():
    hit = poly.kelly(0.6, 0.4, fraction=0.25, cap=0.10)
    assert hit["f"] > 0
    assert hit["edge"] > 0
    miss = poly.kelly(0.4, 0.55)
    assert miss["f"] == 0.0


def test_parse_market():
    row = {
        "id": "1",
        "question": "Will BTC hit 200k in 2026?",
        "slug": "btc-200k",
        "outcomePrices": '["0.22","0.78"]',
        "outcomes": '["Yes","No"]',
        "volume24hr": 120000,
        "liquidity": 50000,
        "closed": False,
    }
    parsed = poly._parse(row)
    assert parsed["yes"] == 0.22
    assert parsed["volume_24h"] == 120000
    assert "polymarket.com" in parsed["url"]


def test_bounce_uses_scan(monkeypatch, tmp_path):
    monkeypatch.setattr(poly.obsidian, "write_note", lambda *a, **k: {"ok": True, "path": "x.md"})
    monkeypatch.setattr(
        poly,
        "scan",
        lambda **k: {
            "ok": True,
            "markets": [
                {
                    "id": "1",
                    "question": "Extreme favorite",
                    "yes": 0.92,
                    "volume_24h": 9e6,
                    "url": "https://polymarket.com",
                    "slug": "x",
                }
            ],
        },
    )
    out = poly.bounce(limit=4, bankroll=1000)
    assert out["ok"] is True
    assert "ideas" in out
    assert out.get("disclaimer")


def test_dispatch_scan_mocked(monkeypatch):
    monkeypatch.setattr(poly, "scan", lambda **k: {"ok": True, "markets": [], "query": k.get("query")})
    out = poly.dispatch("scan", query="fed")
    assert out["ok"] is True
