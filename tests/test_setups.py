from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import setups


def _bars(closes, highs=None, lows=None, vols=None):
    highs = highs or [c * 1.01 for c in closes]
    lows = lows or [c * 0.99 for c in closes]
    vols = vols or [1_000_000] * len(closes)
    return [
        {"t": i, "open": c, "high": highs[i], "low": lows[i], "close": c, "volume": vols[i]}
        for i, c in enumerate(closes)
    ]


def test_catalog_entries_are_complete():
    required = {"name", "idea", "why", "trigger", "invalidation", "stop_rule", "target_rule", "fails_when"}
    for key, entry in setups.CATALOG.items():
        assert required <= set(entry), f"{key} missing {required - set(entry)}"
        assert all(entry[f].strip() for f in required)


def test_teach_lists_then_details():
    listing = setups.teach()
    assert listing["ok"]
    assert len(listing["setups"]) == len(setups.CATALOG)

    one = setups.teach("trend_pullback")
    assert one["ok"]
    assert "invalidation" in one

    assert "error" in setups.teach("nope")


def test_atr_computation():
    bars = _bars([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25])
    atr = setups._atr(bars, period=14)
    assert atr is not None and atr > 0
    assert setups._atr(_bars([1, 2, 3]), period=14) is None


def test_sma_and_swings():
    assert setups._sma([1, 2, 3, 4], 2) == 3.5
    assert setups._sma([1], 5) is None
    bars = _bars([10, 5, 20], highs=[11, 6, 21], lows=[9, 4, 19])
    assert setups._swing_low(bars) == 4
    assert setups._swing_high(bars) == 21


def test_scan_needs_enough_bars(monkeypatch):
    monkeypatch.setattr(setups.markets, "history", lambda s, r: {"bars": _bars([10] * 10)})
    out = setups.scan("AAPL")
    assert "error" in out and "60+" in out["error"]


def test_scan_detects_breakout(monkeypatch):
    # steady climb ending at a new 20-day high on heavy volume
    closes = [100 + i * 0.5 for i in range(80)]
    vols = [1_000_000] * 79 + [3_000_000]
    monkeypatch.setattr(setups.markets, "history", lambda s, r: {"bars": _bars(closes, vols=vols)})
    out = setups.scan("AAPL")
    assert out["ok"]
    keys = {f["setup"] for f in out["found"]}
    assert "breakout_20d" in keys
    breakout = next(f for f in out["found"] if f["setup"] == "breakout_20d")
    assert breakout["confidence"] == "high"


def test_breakout_without_volume_is_low_confidence(monkeypatch):
    closes = [100 + i * 0.5 for i in range(80)]
    monkeypatch.setattr(setups.markets, "history", lambda s, r: {"bars": _bars(closes)})
    out = setups.scan("AAPL")
    breakout = next(f for f in out["found"] if f["setup"] == "breakout_20d")
    assert breakout["confidence"] == "low"
    assert "not confirming" in breakout["evidence"]["note"]


def test_plan_rejects_unknown_setup():
    out = setups.plan("AAPL", "nonsense")
    assert "error" in out
    assert "known" in out


def test_plan_produces_coherent_levels(monkeypatch):
    closes = [100 + i * 0.5 for i in range(80)]
    monkeypatch.setattr(setups.markets, "history", lambda s, r: {"bars": _bars(closes)})
    out = setups.plan("AAPL", "breakout_20d", risk=1000)
    assert out["ok"]
    # a long plan must have stop below entry and target above
    assert out["stop"] < out["entry"] < out["target"]
    assert out["risk_per_share"] > 0
    assert out["shares"] == int(1000 // out["risk_per_share"])
    assert out["total_risk"] <= 1000
    assert "bracket" in out["place"]
    # the teaching travels with the plan
    assert out["invalidation"] and out["fails_when"]


def test_plan_warns_on_thin_reward(monkeypatch):
    closes = [100 + i * 0.5 for i in range(80)]
    monkeypatch.setattr(setups.markets, "history", lambda s, r: {"bars": _bars(closes)})
    out = setups.plan("AAPL", "oversold_in_uptrend", risk=100)
    # target is the 20-day SMA which sits below a rising price -> poor/negative R
    assert "warnings" in out


def test_plan_warns_when_risk_budget_too_small(monkeypatch):
    closes = [100 + i * 0.5 for i in range(80)]
    monkeypatch.setattr(setups.markets, "history", lambda s, r: {"bars": _bars(closes)})
    out = setups.plan("AAPL", "breakout_20d", risk=0.01)
    assert out["shares"] == 0
    assert any("smaller than one share" in w for w in out["warnings"])


def test_dispatch_routing(monkeypatch):
    assert "error" in setups.dispatch("scan")
    assert "error" in setups.dispatch("plan")
    assert setups.dispatch("teach")["ok"]
    assert "error" in setups.dispatch("bogus")
