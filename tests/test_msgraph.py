from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import msgraph, rag


def test_ms_not_ready_without_keys(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MS_CLIENT_ID", "")
    monkeypatch.setattr(config, "MS_REFRESH_TOKEN", "")
    assert msgraph.ready() is False
    out = msgraph.start_device()
    assert out.get("ok") is False


def test_cosine():
    assert rag._cosine([1, 0], [1, 0]) == 1
    assert rag._cosine([1, 0], [0, 1]) == 0


def test_send_mail_blocked(monkeypatch):
    monkeypatch.setattr(msgraph, "access_token", lambda: None)
    out = msgraph.send_mail("a@b.com", "hi", "body")
    assert "error" in out
