"""Health checks must never raise.

A health check that crashes is worthless precisely when you need it — the moment a
subsystem is broken. So the important property is not that it reports the right thing
on a healthy box, but that it survives every subsystem being broken at once and still
names the fix.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import health


def _break_everything(monkeypatch):
    """Every probe raises. Nothing may propagate."""
    import importlib

    real = importlib.import_module

    def boom(name, *a, **k):
        if name.startswith("app.") and name != "app.health":
            raise RuntimeError(f"{name} is broken")
        return real(name, *a, **k)

    monkeypatch.setattr(health.importlib, "import_module", boom)


def test_check_survives_total_failure(monkeypatch):
    _break_everything(monkeypatch)
    out = health.check()
    assert isinstance(out, dict)
    assert out["ok"] is False
    assert out["problems"]


def test_each_probe_survives_total_failure(monkeypatch):
    _break_everything(monkeypatch)
    for fn in (health.brain, health.voice, health.subsystems):
        assert isinstance(fn(), dict), f"{fn.__name__} raised or returned non-dict"


# --- brain path selection -----------------------------------------------------


def test_no_key_reports_no_key_not_none(monkeypatch):
    """'xAI unavailable (None)' told the user nothing."""
    monkeypatch.setattr(health.config, "XAI_API_KEY", "")
    out = health.brain()
    assert out["xai"]["reason"] == "no_key"
    assert "XAI_API_KEY" in out["xai"]["fix"]


def test_offline_short_circuits_to_free_brain(monkeypatch):
    monkeypatch.setattr(health.config, "OFFLINE", True)
    out = health.brain()
    assert out["active_path"] == "free_brain"
    assert "OFFLINE" in out["why"]


def test_working_xai_is_the_active_path(monkeypatch):
    monkeypatch.setattr(health.config, "OFFLINE", False)
    monkeypatch.setattr(health.config, "XAI_API_KEY", "key")
    monkeypatch.setattr(health, "_try", lambda fn, default=None: {"ok": True, "reason": "ready"})
    out = health.brain()
    assert out["active_path"] == "grok"
    assert out["healthy"] is True


def test_rejected_key_is_called_out_as_credits_or_auth(monkeypatch):
    monkeypatch.setattr(health.config, "OFFLINE", False)
    monkeypatch.setattr(health.config, "XAI_API_KEY", "key")
    monkeypatch.setattr(
        health, "_try", lambda fn, default=None: {"ok": False, "reason": "credits_or_auth", "models": []}
    )
    out = health.brain()
    assert "credits" in out["xai"]["fix"].lower()
    assert out["healthy"] is False


def test_ollama_fallback_when_xai_down(monkeypatch):
    monkeypatch.setattr(health.config, "OFFLINE", False)
    monkeypatch.setattr(health.config, "XAI_API_KEY", "")

    def fake_try(fn, default=None):
        return {"ok": True, "models": ["llama3.2"], "reason": "ready"}

    monkeypatch.setattr(health, "_try", fake_try)
    out = health.brain()
    assert out["active_path"] == "ollama"
    assert out["healthy"] is True


def test_ollama_up_but_no_model_is_not_healthy(monkeypatch):
    monkeypatch.setattr(health.config, "OFFLINE", False)
    monkeypatch.setattr(health.config, "XAI_API_KEY", "")
    monkeypatch.setattr(health, "_try", lambda fn, default=None: {"ok": True, "models": []})
    out = health.brain()
    assert out["active_path"] == "free_brain"
    assert out["healthy"] is False
    assert "ollama pull" in out["ollama"]["fix"]


# --- voice --------------------------------------------------------------------


def test_voice_blocked_without_a_key(monkeypatch):
    monkeypatch.setattr(health.config, "XAI_API_KEY", "")
    out = health.voice()
    assert out["ok"] is False
    assert any("XAI_API_KEY" in b for b in out["blockers"])


def test_voice_blocked_when_offline(monkeypatch):
    monkeypatch.setattr(health.config, "XAI_API_KEY", "key")
    monkeypatch.setattr(health.config, "OFFLINE", True)
    monkeypatch.setattr(health, "_try", lambda fn, default=None: {"ok": True, "reason": "ready"})
    out = health.voice()
    assert any("OFFLINE" in b for b in out["blockers"])


def test_voice_flags_a_rejected_key_separately(monkeypatch):
    """A set-but-rejected key kills voice as dead as a missing one, and looks different."""
    monkeypatch.setattr(health.config, "XAI_API_KEY", "key")
    monkeypatch.setattr(health.config, "OFFLINE", False)
    monkeypatch.setattr(health, "_try", lambda fn, default=None: {"ok": False, "reason": "credits_or_auth"})
    out = health.voice()
    assert out["ok"] is False
    assert any("rejected" in b for b in out["blockers"])


def test_voice_ok_when_everything_lines_up(monkeypatch):
    monkeypatch.setattr(health.config, "XAI_API_KEY", "key")
    monkeypatch.setattr(health.config, "OFFLINE", False)
    monkeypatch.setattr(health, "_try", lambda fn, default=None: {"ok": True, "reason": "ready"})
    out = health.voice()
    assert out["ok"] is True
    assert out["blockers"] is None


# --- shape --------------------------------------------------------------------


def test_check_reports_a_verdict():
    out = health.check()
    assert "verdict" in out
    assert "brain" in out and "voice" in out and "subsystems" in out


def test_every_problem_is_a_readable_string():
    for p in health.check().get("problems") or []:
        assert isinstance(p, str) and len(p) > 10


def test_dispatch_surface():
    assert health.dispatch("check")["verdict"]
    assert "active_path" in health.dispatch("brain")
    assert "checks" in health.dispatch("voice")
    assert "error" in health.dispatch("nonsense")
