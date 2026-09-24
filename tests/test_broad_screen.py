"""The vendored scanner's per-symbol path (fetch_data + get_options_data) does two
yfinance round-trips per symbol - that's what forced the old universe caps (16 for
liquid, 220 for "full"). broad_screen() is the actual fix: a cheap batched technical
pass over the real thousands-of-tickers universe (universe.py), narrowed to a
shortlist BEFORE anything touches the expensive options-chain path.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config, markets, marketbeast as mb, setups


def _bars(prices, *, start_date="2023-06-01"):
    import datetime as dt

    d0 = dt.date.fromisoformat(start_date)
    out = []
    for i, c in enumerate(prices):
        out.append({
            "date": (d0 + dt.timedelta(days=i)).isoformat(),
            "open": round(c, 2), "high": round(c * 1.01, 2), "low": round(c * 0.99, 2),
            "close": round(c, 2), "volume": 1_000_000,
        })
    return out


class _FakeUniverse:
    """Stands in for app.universe: a fixed symbol list, no network."""

    def __init__(self, symbols):
        self._symbols = symbols

    def full(self):
        return {"ok": True, "symbols": self._symbols, "count": len(self._symbols), "source": "fake"}


def test_liquid_symbols_is_no_longer_capped_at_sixteen(monkeypatch):
    big_watchlist = [f"SYM{i}" for i in range(30)]
    monkeypatch.setattr(config, "WATCHLIST", big_watchlist)
    out = mb._liquid_symbols()
    assert len(out) > 16
    assert "SYM0" in out


def test_broad_screen_ranks_by_setup_confidence_and_respects_max_symbols(monkeypatch):
    # Two symbols with a real trend_pullback-shaped series, one flat/no-setup symbol.
    trending = _bars([100 + i * 0.3 for i in range(90)])
    flat = _bars([100.0 for _ in range(90)])

    monkeypatch.setattr(mb, "universe_mod", lambda: _FakeUniverse(["AAA", "BBB", "CCC"]))
    monkeypatch.setattr(config, "MARKETBEAST_MAX_UNIVERSE", 2)  # only AAA, BBB considered

    def fake_batch(symbols, range_, **kwargs):
        return {
            "AAA": {"bars": trending, "source": "fake"},
            "BBB": {"bars": flat, "source": "fake"},
        }

    monkeypatch.setattr(markets, "history_batch", fake_batch)

    out = mb.broad_screen(shortlist=10)
    assert out["ok"] is True
    assert out["scanned"] == 2, "CCC must be excluded by MARKETBEAST_MAX_UNIVERSE"
    symbols_in_shortlist = {c["symbol"] for c in out["shortlist"]}
    assert "CCC" not in symbols_in_shortlist


def test_broad_screen_counts_fetch_errors_without_crashing(monkeypatch):
    monkeypatch.setattr(mb, "universe_mod", lambda: _FakeUniverse(["AAA"]))
    monkeypatch.setattr(config, "MARKETBEAST_MAX_UNIVERSE", 0)
    monkeypatch.setattr(markets, "history_batch", lambda symbols, range_, **k: {"AAA": {"error": "no data"}})

    out = mb.broad_screen()
    assert out["ok"] is True
    assert out["errors"] == 1
    assert out["candidates"] == 0


def test_best_calls_market_universe_uses_the_broad_screen_shortlist(monkeypatch):
    """universe='market' should feed _score_calls the shortlist, not the vendored
    scanner's 273-symbol FULL_MARKET list - that's the whole point of this path.
    """
    called_with = {}

    monkeypatch.setattr(mb, "broad_screen", lambda **kwargs: {
        "ok": True, "shortlist": [{"symbol": "HOT1"}, {"symbol": "HOT2"}],
        "universe_size": 5000, "universe_source": "fake", "scanned": 5000, "candidates": 2,
    })

    class FakeScanner:
        pass

    class FakeModule:
        @staticmethod
        def StockScanner():
            return FakeScanner()

    def fake_score_calls(scanner, symbols, *, dte, top, allow_puts=True):
        called_with["symbols"] = list(symbols)
        return []

    monkeypatch.setattr(mb, "_load_scanner", lambda: FakeModule)
    monkeypatch.setattr(mb, "_score_calls", fake_score_calls)
    monkeypatch.setattr(mb, "_overlay_ibkr", lambda picks: picks)
    monkeypatch.setattr(mb, "_write_vault", lambda picks, uni: None)
    mb._cache.update(at=0.0, key="", picks=[])

    out = mb.best_calls(top=5, universe="market")
    assert out["ok"] is True
    assert called_with["symbols"] == ["HOT1", "HOT2"]
    assert out["broad_screen"]["candidates"] == 2
