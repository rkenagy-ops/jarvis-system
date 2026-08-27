"""Half the signal was computed and thrown away.

The scanner scores both directions and populates preferred_puts. The wrapper filtered
to BULLISH/NEUTRAL, read only preferred_calls, and hardcoded CALL - so every bearish
read produced nothing at all, and the put side of the engine had never once been used.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import marketbeast as mb

SRC = (ROOT / "app" / "marketbeast.py").read_text(encoding="utf-8")


class FakeScanner:
    """Minimal stand-in: a direction, and both sides of a chain."""

    def __init__(self, direction):
        self.direction = direction

    def fetch_data(self, symbol):
        return list(range(50))  # any sequence of length >= 20

    def analyze(self, symbol, df):
        return {"symbol": symbol, "direction": self.direction, "score": 0.8, "price": 100}

    def get_options_data(self, symbol, target_dte=7):
        return {
            "expiration": "20991231", "dte": target_dte, "iv": 0.3,
            "preferred_calls": [{"strike": 105, "price": 2.0, "bid": 1.95, "ask": 2.05,
                                 "delta": 0.45, "oi": 900, "volume": 300, "score": 70}],
            "preferred_puts": [{"strike": 95, "price": 2.0, "bid": 1.95, "ask": 2.05,
                                "delta": -0.45, "oi": 900, "volume": 300, "score": 70}],
        }


def test_a_bearish_read_now_produces_a_put():
    row = mb._analyze_one(FakeScanner("BEARISH"), "TEST", 30)
    assert row is not None, "a bearish signal used to produce nothing at all"
    assert row["option_type"] == "PUT"
    assert row["strike"] == 95


def test_a_bullish_read_still_produces_a_call():
    row = mb._analyze_one(FakeScanner("BULLISH"), "TEST", 30)
    assert row["option_type"] == "CALL"
    assert row["strike"] == 105


def test_puts_can_be_switched_off_for_a_long_only_book():
    assert mb._analyze_one(FakeScanner("BEARISH"), "TEST", 30, allow_puts=False) is None


def test_a_put_breaks_even_below_the_strike():
    """Adding the debit on both sides put every put's breakeven on the wrong side."""
    row = mb.enrich({"symbol": "X", "option_type": "PUT", "strike": 100,
                     "option_price": 4.0, "bid": 3.9, "ask": 4.1, "delta": -0.45, "oi": 900})
    assert row["breakeven"] == 96.0


def test_a_call_breaks_even_above_the_strike():
    row = mb.enrich({"symbol": "X", "option_type": "CALL", "strike": 100,
                     "option_price": 4.0, "bid": 3.9, "ask": 4.1, "delta": 0.45, "oi": 900})
    assert row["breakeven"] == 104.0


def test_the_put_side_of_the_chain_is_actually_read():
    assert "preferred_puts" in SRC, "the scanner has always populated this; read it"


def test_the_vault_note_does_not_label_every_pick_a_call():
    assert "MarketBeast picks" in SRC
    assert "MarketBeast calls" not in SRC


def test_an_unknown_direction_is_skipped_rather_than_guessed():
    assert mb._analyze_one(FakeScanner("SIDEWAYS-ISH"), "TEST", 30) is None
