"""The vendored MarketBeast scanner's 'full market' list is 273 hardcoded symbols -
raising a truncation limit on top of it can never produce a scan of thousands of
stocks. This is the actual source for that: Nasdaq's free public symbol directory,
cached, with the old 273-symbol list kept only as a safety net if the fetch fails.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import universe

NASDAQLISTED_SAMPLE = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
    "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N\n"
    "ZZZT|Test Issue - Do Not Trade|Q|Y|N|100|N|N\n"
    "MSFT|Microsoft Corporation - Common Stock|Q|N|N|100|N|N\n"
    "File Creation Time: 0901202400:00|||||||\n"
)

OTHERLISTED_SAMPLE = (
    "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n"
    "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY\n"
    "BRK.A|Berkshire Hathaway Inc|N|BRK.A|N|100|N|BRK.A\n"
    "File Creation Time: 0901202400:00||||||\n"
)


def test_nasdaqlisted_parser_drops_test_issues():
    out = universe._parse_nasdaqlisted(NASDAQLISTED_SAMPLE)
    assert "AAPL" in out and "MSFT" in out
    assert "ZZZT" not in out


def test_otherlisted_parser_drops_test_issues():
    out = universe._parse_otherlisted(OTHERLISTED_SAMPLE)
    assert "SPY" in out


def test_fetch_from_nasdaq_drops_non_plain_tickers(monkeypatch):
    calls = {"n": 0}

    def fake_fetch_one(url):
        calls["n"] += 1
        return NASDAQLISTED_SAMPLE if "nasdaqlisted" in url else OTHERLISTED_SAMPLE

    monkeypatch.setattr(universe, "_fetch_one", fake_fetch_one)
    out = universe._fetch_from_nasdaq()
    assert calls["n"] == 2
    assert "AAPL" in out and "MSFT" in out and "SPY" in out
    assert "BRK.A" not in out, "class-share tickers with punctuation aren't plain equity symbols"
    assert "ZZZT" not in out


def test_full_writes_and_reads_the_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(universe, "_CACHE_PATH", tmp_path / "universe_cache.json")
    monkeypatch.setattr(universe, "_fetch_from_nasdaq", lambda: ["AAPL", "MSFT", "SPY"])

    first = universe.full()
    assert first["ok"] and first["source"] == "nasdaq" and first["cached"] is False
    assert first["count"] == 3

    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise AssertionError("must not refetch within the cache TTL")

    monkeypatch.setattr(universe, "_fetch_from_nasdaq", boom)
    second = universe.full()
    assert second["cached"] is True
    assert calls["n"] == 0
    assert second["symbols"] == ["AAPL", "MSFT", "SPY"]


def test_full_falls_back_to_stale_cache_when_nasdaq_is_down(monkeypatch, tmp_path):
    monkeypatch.setattr(universe, "_CACHE_PATH", tmp_path / "universe_cache.json")
    monkeypatch.setattr(universe, "_fetch_from_nasdaq", lambda: ["AAPL"])
    universe.full()  # seed the cache

    def boom():
        raise RuntimeError("Nasdaq is down")

    monkeypatch.setattr(universe, "_fetch_from_nasdaq", boom)
    monkeypatch.setattr(universe, "_CACHE_TTL", 0)  # force the cache to read as stale
    out = universe.full()
    assert out["ok"] is True
    assert out["symbols"] == ["AAPL"]
    assert "warning" in out


def test_full_falls_back_to_vendored_list_with_no_cache_at_all(monkeypatch, tmp_path):
    monkeypatch.setattr(universe, "_CACHE_PATH", tmp_path / "nonexistent_cache.json")

    def boom():
        raise RuntimeError("Nasdaq is down")

    monkeypatch.setattr(universe, "_fetch_from_nasdaq", boom)
    monkeypatch.setattr(universe, "_fallback_universe", lambda: ["AAPL", "MSFT"])

    out = universe.full()
    assert out["ok"] is True
    assert out["source"] == "vendored_fallback"
    assert out["symbols"] == ["AAPL", "MSFT"]
    assert "warning" in out


def test_status_reports_no_cache_cleanly(monkeypatch, tmp_path):
    monkeypatch.setattr(universe, "_CACHE_PATH", tmp_path / "nonexistent.json")
    out = universe.status()
    assert out["ok"] is True and out["cached"] is False


def test_dispatch_routes_actions(monkeypatch, tmp_path):
    monkeypatch.setattr(universe, "_CACHE_PATH", tmp_path / "universe_cache.json")
    monkeypatch.setattr(universe, "_fetch_from_nasdaq", lambda: ["AAPL"])
    assert universe.dispatch("full")["ok"] is True
    assert universe.dispatch("status")["ok"] is True
    out = universe.dispatch("nonsense")
    assert "error" in out
