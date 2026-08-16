from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config, guard


def test_bind_stays_loopback(monkeypatch):
    monkeypatch.setattr(config, "HOST", "0.0.0.0")
    monkeypatch.setattr(config, "JARVIS_ALLOW_LAN", False)
    assert guard.bind_host() == "127.0.0.1"
    monkeypatch.setattr(config, "HOST", "127.0.0.1")
    assert guard.bind_host() == "127.0.0.1"


def test_host_header():
    assert guard.host_ok("127.0.0.1:8787")
    assert guard.host_ok("localhost")
    assert not guard.host_ok("evil.example")


def test_token_compare(monkeypatch):
    monkeypatch.setattr(config, "JARVIS_TOKEN", "secret-token-value")
    assert guard.token_ok("secret-token-value")
    assert not guard.token_ok("nope")
    assert not guard.token_ok("")


def test_ssrf_block():
    assert not guard.allow_url("http://127.0.0.1/secret")
    assert not guard.allow_url("http://localhost:8787/api/settings")
    assert not guard.allow_url("http://10.0.0.5/")
    assert not guard.allow_url("file:///etc/passwd")
    assert guard.allow_url("https://example.com/page")


def test_posture_has_vpn_note():
    p = guard.posture()
    assert p["loopback_only"] or p["bind"] == "127.0.0.1"
    assert "VPN" in p["vpn_note"]
