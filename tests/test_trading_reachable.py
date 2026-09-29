"""The trading tools must be reachable from every brain, not just Grok.

Free mode is a keyword router and Ollama gets a truncated tool list; before this, both
silently had no path to the hunter, candles or journal.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import brain, candles, free_brain, hunter, journal, setups


def test_ollama_gets_the_trading_tools_for_a_trading_question():
    names = [t["name"] for t in brain._ollama_tools("jarvis", "any breakout on NVDA candles?")]
    assert len(names) <= brain.OLLAMA_TOOL_LIMIT
    assert {"hunter", "candles", "setups", "journal"} <= set(names)
    assert {"hunter", "candles"} <= {t["name"] for t in brain._ollama_tools("trader", "hello")}


def test_free_brain_routes_the_hunt(monkeypatch):
    monkeypatch.setattr(hunter, "last", lambda: {
        "ok": True, "at": "2026-09-29T20:00:00", "session": "post", "universe": {"liquid": 1500}, "signals": 40,
        "longs": [{"symbol": "AAA", "setup": "breakout_20d", "score": 5, "entry": 10, "stop": 9, "target": 13,
                   "r_multiple": 3, "rvol": 2}],
        "shorts": [], "loading": []})
    out = free_brain.handle("show me the top longs from the hunter")
    assert "AAA" in out["text"] and out["calls"][0]["name"] == "hunter"


def test_free_brain_routes_the_journal(monkeypatch):
    monkeypatch.setattr(journal, "insights", lambda: {
        "closed": 0, "overall": {"trades": 0}, "best": [], "worst": [], "rules": [], "edges": [], "mistake_cost_r": {}})
    out = free_brain.handle("what mistakes have you made")
    assert out["calls"][0]["name"] == "journal"


def test_free_brain_routes_a_chart_read(monkeypatch):
    monkeypatch.setattr(candles, "radar", lambda s: {"status": "breaking_out", "direction": "up", "close": 10,
                                                     "rvol": 2.0, "long_trigger": 10.1, "short_trigger": 8})
    monkeypatch.setattr(candles, "read", lambda s: {"patterns": [{"pattern": "hammer", "strength": "strong"}], "lean": "bull"})
    monkeypatch.setattr(setups, "scan", lambda s: {"found": [{"setup": "breakout_20d", "confidence": "high"}]})
    out = free_brain.handle("read the candles on NVDA")
    assert "NVDA breaking_out" in out["text"].replace("**", "") and "hammer" in out["text"]


def test_she_can_list_every_tool_in_free_mode():
    from app import tools

    for ask in ("what tools do you have", "list all tools", "what can you do"):
        out = free_brain.handle(ask)
        for name in ("hunter", "candles", "journal", "setups", "market"):
            assert f"- {name}:" in out["text"], f"{ask!r} does not mention {name}"
    assert len(tools.roster("jarvis")) >= 48


def test_her_prompt_names_the_new_tools():
    from app.agents import conductor_system, specialist_system

    for text in (conductor_system(""), specialist_system("trader", "")):
        assert "hunter" in text and "candles" in text and "journal" in text
