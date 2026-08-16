from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import feeds, tools


RSS = """<?xml version="1.0"?>
<rss><channel>
<item><title>Alpha moves</title><link>https://example.com/a</link><pubDate>Tue, 16 Aug 2026 12:00:00 GMT</pubDate></item>
<item><title>Beta holds</title><link>https://example.com/b</link></item>
</channel></rss>
"""


def test_parse_rss():
    rows = feeds._parse_feed(RSS, "bbc")
    assert rows[0]["title"] == "Alpha moves"
    assert rows[0]["source"] == "bbc"
    assert rows[0]["link"].startswith("https://")


def test_snapshot_uses_cache(monkeypatch):
    calls = {"n": 0}

    def fake_news(source, url):
        calls["n"] += 1
        return [{"source": source, "title": f"{source} one", "link": "https://example.com", "when": ""}]

    monkeypatch.setattr(feeds, "_pull_news", fake_news)
    monkeypatch.setattr(feeds, "_quotes", lambda: [{"symbol": "SPY", "price": 1, "change_pct": 0.1}])
    feeds._cache["at"] = 0
    feeds._cache["data"] = None
    a = feeds.snapshot(force=True)
    b = feeds.snapshot()
    assert a["news"]
    assert a["quotes"][0]["symbol"] == "SPY"
    assert b is a
    assert "feeds" in {t.get("name") for t in tools.tools_for("jarvis", allow_spawn=True)}
