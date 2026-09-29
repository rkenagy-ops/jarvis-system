"""Candle reading must name the shape correctly, grade it by where it formed, and tell a
breakout from a breakdown - off bars alone, so the backtest can use it with no look-ahead."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import candles, setups


def _bar(o, h, l, c, v=1_000_000, d=0):
    return {"date": f"2024-01-{d:02d}", "open": o, "high": h, "low": l, "close": c, "volume": v}


def _trend(n, start, step, vol=1_000_000):
    out = []
    for i in range(n):
        c = start + i * step
        out.append({"date": f"d{i}", "open": c - step / 2, "high": c + 0.5, "low": c - 0.5, "close": c, "volume": vol})
    return out


def test_every_catalog_pattern_is_documented():
    for key, entry in candles.CATALOG.items():
        assert {"bias", "what", "where", "confirm", "fails_when"} <= set(entry), key
        assert entry["bias"] in {"bull", "bear", "neutral"}
    assert candles.teach()["ok"]
    assert "error" in candles.teach("not_a_pattern")


def test_hammer_after_a_decline_but_hanging_man_after_an_advance():
    shape = _bar(99, 100.6, 96, 100.4)  # small body at the top, long lower wick
    down = _trend(10, 110, -1)
    up = _trend(10, 90, 1)
    assert "hammer" in candles._shapes_at(down + [shape], 10)
    assert "hanging_man" in candles._shapes_at(up + [shape], 10)


def test_engulfing_both_directions():
    base = _trend(10, 100, 0)
    bull = base + [_bar(101, 101.5, 99.5, 100), _bar(99.8, 102, 99.6, 101.5)]
    bear = base + [_bar(100, 101.5, 99.5, 101), _bar(101.2, 101.4, 99, 99.6)]
    assert "bullish_engulfing" in candles._shapes_at(bull, 11)
    assert "bearish_engulfing" in candles._shapes_at(bear, 11)


def test_inside_bar_and_morning_star():
    base = _trend(10, 100, 0)
    inside = base + [_bar(100, 104, 96, 101), _bar(100.5, 102, 98, 101)]
    assert "inside_bar" in candles._shapes_at(inside, 11)

    star = _trend(10, 110, -1) + [_bar(100, 100.5, 94, 94.5), _bar(94, 94.8, 93.2, 94.2), _bar(94.5, 99, 94.3, 98.8)]
    assert "morning_star" in candles._shapes_at(star, 12)


def test_read_grades_a_bullish_candle_at_support_above_the_bars_it_ignores():
    bars = _trend(60, 100, 0.2) + _trend(8, 112, -0.6)
    bars.append(_bar(106, 107.6, 103, 107.5, v=3_000_000))  # hammer on heavy volume near the low
    out = candles.read_bars(bars)
    assert out["ok"]
    hammer = [p for p in out["patterns"] if p["pattern"] == "hammer"]
    assert hammer and hammer[0]["score"] >= 2
    assert "volume above average" in hammer[0]["why"]


def test_radar_calls_breakouts_and_breakdowns_by_direction_and_volume():
    flat = [_bar(100, 101, 99, 100) for _ in range(80)]
    up = candles.radar_bars(flat + [_bar(100, 104, 100, 103.5, v=3_000_000)])
    down = candles.radar_bars(flat + [_bar(100, 100, 96, 96.5, v=3_000_000)])
    quiet = candles.radar_bars(flat + [_bar(100, 104, 100, 103.5, v=900_000)])
    assert up["status"] == "breaking_out" and up["direction"] == "up"
    assert down["status"] == "breaking_down" and down["direction"] == "down"
    assert quiet["status"] == "breaking_out_light_volume"
    assert up["long_trigger"] > up["prior_20d_high"] and up["short_trigger"] < up["prior_20d_low"]


def test_squeeze_percentile_flags_a_coil():
    wide = [100 + (5 if i % 2 else -5) for i in range(120)]
    tight = [100 + (0.1 if i % 2 else -0.1) for i in range(20)]
    assert candles.squeeze_percentile(wide + tight) <= 20
    assert candles.squeeze_percentile(tight + wide) > 20


def test_breakdown_is_detected_as_a_short_with_levels_on_the_right_side():
    closes = [100.0] * 70 + [99.0, 98.0, 94.0]
    bars = [
        {"date": f"d{i}", "open": c + 0.5, "high": c + 1, "low": c - 1, "close": c,
         "volume": 3_000_000 if i == len(closes) - 1 else 1_000_000}
        for i, c in enumerate(closes)
    ]
    ctx = setups.context_from_bars(bars, "DROP")
    found = {f["setup"]: f for f in setups.detect(ctx)["found"]}
    assert "breakdown_20d" in found and found["breakdown_20d"]["side"] == "sell"
    levels = setups.levels_for(ctx, "breakdown_20d")
    assert levels["side"] == "sell"
    assert levels["stop"] > levels["entry"] > levels["target"]
