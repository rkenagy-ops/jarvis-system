from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import markets, memory, widgets, workspace


def test_calc_and_jail():
    assert widgets.calc("2+2")["result"] == 4
    assert "error" in widgets.calc("__import__('os')")
    assert "error" in workspace.dispatch("read", path="../../Windows/system32/cmd.exe")


def test_indicators():
    closes = [100 + i + (i % 3) for i in range(60)]
    stats = markets.indicators(closes)
    assert stats["last"] == closes[-1]
    assert 0 <= stats["rsi14"] <= 100
    assert stats["sma20"]


def test_paper_trade_and_confirm(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "m.db")
    monkeypatch.setattr(markets.config, "DB_PATH", tmp_path / "m.db")
    monkeypatch.setattr(markets.config, "TRADING_MODE", "paper")
    monkeypatch.setattr(markets.config, "TRADING_REQUIRE_CONFIRMATION", True)
    memory.init()
    markets.init()
    monkeypatch.setattr(markets, "quote", lambda symbol: {"symbol": symbol, "price": 10.0})
    fill = markets.paper_trade("TEST", "buy", 3)
    assert fill.get("ok")
    acc = markets.account()
    assert any(p["symbol"] == "TEST" for p in acc["positions"])
    monkeypatch.setattr(markets.config, "TRADING_MODE", "live")
    blocked = markets.paper_trade("TEST", "buy", 1)
    assert blocked.get("blocked")
    assert blocked.get("confirm_token")


def test_memory_grows_skills(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "m.db")
    memory.init()
    memory.learn_from_turn("buy aapl?", "checking quote", [{"name": "market_quote"}])
    names = {s["name"] for s in memory.list_skills()}
    assert "markets" in names
    memory.add_goal("Scan NVDA", "daily")
    assert any("NVDA" in g["title"] for g in memory.list_goals())


def test_analyst_in_swarm():
    from app import agents, tools
    assert "analyst" in agents.AGENTS
    names = {t.get("name") or t.get("type") for t in tools.tools_for("jarvis", allow_spawn=True)}
    assert "market" in names
    assert "workspace" in names
    assert "wiki" in names
