"""The hunter ranks both directions off one batched fetch, never places anything, and
only logs signals to the tracker when told to (after the close by default)."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import autonomy, forward_tracker, hunter, markets


def _bars(closes, last_vol=3_000_000):
    return [
        {"date": f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", "open": c, "high": c + 1, "low": c - 1, "close": c,
         "volume": last_vol if i == len(closes) - 1 else 1_000_000}
        for i, c in enumerate(closes)
    ]


# Wide swings, then a tight coil, then a heavy-volume break out of it - either way.
COIL = [100 + (3 if i % 2 else -3) for i in range(60)] + [100 + (0.3 if i % 2 else -0.3) for i in range(20)]
UP = _bars(COIL + [104.0])
DOWN = _bars(COIL + [96.0])
FLAT = _bars([100.0] * 81, last_vol=1_000_000)


def _fake(monkeypatch, *, session="regular"):
    monkeypatch.setattr(hunter, "liquid_universe", lambda refresh=False: {
        "symbols": ["UPPP", "DOWN", "FLAT"], "listed": 3, "source": "fake"})
    monkeypatch.setattr(markets, "history_batch", lambda symbols, range_, **k: {
        "UPPP": {"bars": UP}, "DOWN": {"bars": DOWN}, "FLAT": {"bars": FLAT}})
    monkeypatch.setattr(forward_tracker, "market_regime", lambda: {"up": True})
    monkeypatch.setattr(hunter, "session", lambda now=None: session)
    monkeypatch.setattr(hunter, "_publish", lambda result: None)
    monkeypatch.setattr(hunter, "LAST_PATH", hunter.config.DATA_DIR / "hunt_last_test.json")


def test_hunt_finds_longs_and_shorts(monkeypatch):
    _fake(monkeypatch)
    out = hunter.hunt(log=False)
    assert out["ok"]
    assert "UPPP" in {r["symbol"] for r in out["longs"]}
    assert "DOWN" in {r["symbol"] for r in out["shorts"]}
    assert "FLAT" not in {r["symbol"] for r in out["longs"] + out["shorts"]}
    for r in out["longs"]:
        assert r["stop"] < r["entry"] < r["target"]
    for r in out["shorts"]:
        assert r["target"] < r["entry"] < r["stop"]


def test_intraday_passes_do_not_log_half_formed_bars(monkeypatch):
    _fake(monkeypatch, session="regular")
    called = []
    monkeypatch.setattr(forward_tracker, "log_from_context", lambda *a, **k: called.append(1) or {"logged": []})
    hunter.hunt()
    assert not called


def test_after_the_close_top_signals_are_logged_for_grading(monkeypatch):
    _fake(monkeypatch, session="post")
    out = hunter.hunt()
    assert out["logged_to_tracker"] >= 2
    with forward_tracker._db() as conn:
        sources = {r["source"] for r in conn.execute("SELECT source FROM forward_signals WHERE symbol IN ('UPPP','DOWN')")}
    assert sources == {"hunter"}


def test_session_boundaries():
    import datetime as dt

    ny = hunter.dt.timezone(dt.timedelta(hours=-4))
    assert hunter.session(dt.datetime(2026, 9, 29, 10, 0, tzinfo=ny)) == "regular"
    assert hunter.session(dt.datetime(2026, 9, 29, 8, 0, tzinfo=ny)) == "pre"
    assert hunter.session(dt.datetime(2026, 9, 29, 17, 0, tzinfo=ny)) == "post"
    assert hunter.session(dt.datetime(2026, 10, 3, 12, 0, tzinfo=ny)) == "closed"


def test_a_slow_job_no_longer_blocks_the_beat(monkeypatch):
    import threading

    release = threading.Event()
    monkeypatch.setattr(autonomy.memory, "due_jobs", lambda: [{"id": "slow1", "name": "bot-28-hunter"}])
    monkeypatch.setattr(autonomy.memory, "mark_job", lambda *a: None)
    monkeypatch.setitem(autonomy.JOB_HANDLERS, "bot-28-hunter", lambda: release.wait(5) and "done")
    monkeypatch.setattr(autonomy.config, "AUTONOMY_ENABLED", True)

    first = autonomy.beat()
    second = autonomy.beat()  # still running: must not start a duplicate
    assert "started bot-28-hunter" in first
    assert "started bot-28-hunter" not in second
    assert "slow1" in autonomy.running()
    release.set()
