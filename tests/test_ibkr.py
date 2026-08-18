from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import ibkr, marketbeast


def test_ibkr_host_is_loopback():
    assert ibkr.host() == "127.0.0.1"


def test_live_option_blocked_without_confirm(monkeypatch):
    monkeypatch.setattr(ibkr, "live_cash", lambda: True)
    monkeypatch.setattr(ibkr, "port", lambda: 7496)
    out = ibkr.place_option("NVDA", "20260821", 180, "C", 1)
    assert out.get("blocked") is True
    assert "token" in out or "confirm" in (out.get("reason") or "").lower()


def test_marketbeast_root_detected():
    info = marketbeast.ready()
    assert "root" in info
    assert "ok" in info


def test_bad_expiry():
    monkeypatch_port = ibkr.port
    out = ibkr.place_option("NVDA", "08-21", 180, "C", 1)
    assert "error" in out
    _ = monkeypatch_port
