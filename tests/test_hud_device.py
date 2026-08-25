"""Persistent HUD window and pywinauto device control.

Neither can be exercised for real here: pywinauto is Windows-only and will not install
on Linux, and pywebview needs a display. So these test everything AROUND the untestable
part — backend selection, URL and token handling, the subprocess launch, argument
validation, and every degradation path — and the real window stays the user's to verify.

The degradation paths matter most. A missing library must produce a clear error with the
fix in it, never a traceback and never a silent no-op that looks like success.
"""

from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from app import desktop, hud


def _no_module(monkeypatch, *names):
    """Make the named modules unimportable, whatever is really installed."""
    import builtins

    real = builtins.__import__

    def fake(name, *a, **k):
        if name in names or name.split(".")[0] in names:
            raise ImportError(f"no {name}")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)


def _fake_module(monkeypatch, name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


# --- HUD backend selection ---------------------------------------------------


def test_backend_none_when_nothing_installed(monkeypatch):
    _no_module(monkeypatch, "webview", "nicegui")
    assert hud.backend() is None
    assert hud.available() is False


def test_backend_prefers_pywebview(monkeypatch):
    _fake_module(monkeypatch, "webview")
    _fake_module(monkeypatch, "nicegui")
    assert hud.backend() == "pywebview"


def test_backend_falls_back_to_nicegui(monkeypatch):
    _fake_module(monkeypatch, "nicegui")
    _no_module(monkeypatch, "webview")
    assert hud.backend() == "nicegui"


# --- URL and token -----------------------------------------------------------


def test_hud_url_carries_the_guard_token(monkeypatch):
    monkeypatch.setattr(hud.guard, "token", lambda: "SECRET123")
    url = hud.hud_url()
    assert url.startswith("http://127.0.0.1:")
    assert "token=SECRET123" in url


def test_hud_url_without_token_is_clean():
    assert "token=" not in hud.hud_url(with_token=False)


def test_hud_url_survives_a_token_failure(monkeypatch):
    def boom():
        raise RuntimeError("no token yet")

    monkeypatch.setattr(hud.guard, "token", boom)
    assert hud.hud_url().startswith("http://127.0.0.1:")


def test_hud_url_uses_the_configured_port(monkeypatch):
    monkeypatch.setattr(hud.config, "PORT", 9999)
    assert ":9999/" in hud.hud_url(with_token=False)


# --- launch paths ------------------------------------------------------------


def test_launch_without_a_backend_names_the_fix(monkeypatch):
    _no_module(monkeypatch, "webview", "nicegui")
    out = hud.launch()
    assert out["ok"] is False
    assert "pip install pywebview" in out["fix"]


def test_launch_opens_a_window_with_pywebview(monkeypatch):
    calls = {}

    def create_window(title, url, **kw):
        calls["title"] = title
        calls["url"] = url
        calls["kw"] = kw

    _fake_module(monkeypatch, "webview", create_window=create_window, start=lambda: calls.setdefault("started", True))
    monkeypatch.setattr(hud.guard, "token", lambda: "T")

    out = hud.launch()
    assert out["ok"] is True
    assert calls["title"] == hud.TITLE
    assert "token=T" in calls["url"]
    assert calls["started"] is True


def test_nicegui_alone_is_reported_as_insufficient(monkeypatch):
    _fake_module(monkeypatch, "nicegui")
    _no_module(monkeypatch, "webview")
    out = hud.launch()
    assert out["ok"] is False
    assert "pywebview" in out["fix"]


def test_launch_detached_spawns_a_child(monkeypatch):
    seen = {}

    class FakeProc:
        pid = 4321

    def fake_popen(cmd, **kw):
        seen["cmd"] = cmd
        seen["kw"] = kw
        return FakeProc()

    _fake_module(monkeypatch, "webview")
    monkeypatch.setattr(hud.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(hud.guard, "token", lambda: "T")

    out = hud.launch_detached()
    assert out["ok"] is True and out["pid"] == 4321
    assert seen["cmd"][1:3] == ["-m", "app.hud"], "child must run the hud entry point"
    assert "token=T" in seen["cmd"][3]


def test_launch_detached_reports_a_spawn_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("cannot spawn")

    _fake_module(monkeypatch, "webview")
    monkeypatch.setattr(hud.subprocess, "Popen", boom)
    out = hud.launch_detached()
    assert out["ok"] is False and "cannot spawn" in out["error"]


def test_launch_detached_without_backend(monkeypatch):
    _no_module(monkeypatch, "webview", "nicegui")
    out = hud.launch_detached()
    assert out["ok"] is False
    assert "pywebview" in out["fix"]


def test_hud_dispatch():
    assert hud.dispatch("status")["ok"] is True
    assert "error" in hud.dispatch("nonsense")


# --- pywinauto device control ------------------------------------------------


def test_ui_unavailable_off_windows(monkeypatch):
    monkeypatch.setattr(desktop.platform, "system", lambda: "Linux")
    assert desktop.ui_available() is False
    out = desktop.list_windows()
    assert "Windows-only" in out["error"]


def test_ui_unavailable_without_pywinauto(monkeypatch):
    monkeypatch.setattr(desktop.platform, "system", lambda: "Windows")
    _no_module(monkeypatch, "pywinauto")
    assert desktop.ui_available() is False
    out = desktop.focus_window("Notepad")
    assert "pip install pywinauto" in out["fix"]


def test_every_ui_action_degrades_cleanly(monkeypatch):
    """No pywinauto must never raise, and never look like it worked."""
    monkeypatch.setattr(desktop, "ui_available", lambda: False)
    monkeypatch.setattr(desktop.platform, "system", lambda: "Windows")
    for out in (
        desktop.list_windows(),
        desktop.focus_window("x"),
        desktop.send_keys("hi", window="x"),
        desktop.window_text("x"),
    ):
        assert "error" in out
        assert out.get("ok") is not True


def test_send_keys_validates_before_touching_the_desktop():
    assert "error" in desktop.send_keys("")
    out = desktop.send_keys("x" * 501)
    assert "cap is 500" in out["error"]


def test_focus_and_read_require_a_title(monkeypatch):
    monkeypatch.setattr(desktop, "ui_available", lambda: True)
    assert "error" in desktop.focus_window("")
    assert "error" in desktop.window_text("")


def test_send_keys_does_not_type_when_focus_fails(monkeypatch):
    """Typing into whatever happens to be in front is the failure mode to avoid."""
    monkeypatch.setattr(desktop, "ui_available", lambda: True)
    monkeypatch.setattr(desktop, "focus_window", lambda t: {"error": "no such window"})

    def must_not_import(*a, **k):
        raise AssertionError("should not reach the keyboard driver")

    monkeypatch.setattr(desktop, "_ui_unavailable", must_not_import)
    out = desktop.send_keys("rm -rf", window="Missing")
    assert "error" in out and out.get("ok") is not True


def test_ui_status_is_honest(monkeypatch):
    monkeypatch.setattr(desktop, "ui_available", lambda: False)
    monkeypatch.setattr(desktop.platform, "system", lambda: "Linux")
    st = desktop.ui_status()
    assert st["pywinauto"] is False
    assert st["actions"] == []


def test_desktop_dispatch_routes_the_new_actions(monkeypatch):
    monkeypatch.setattr(desktop, "list_windows", lambda limit=30: {"marker": "windows"})
    monkeypatch.setattr(desktop, "focus_window", lambda t: {"marker": "focus", "title": t})
    monkeypatch.setattr(desktop, "send_keys", lambda k, window="": {"marker": "type", "keys": k})
    monkeypatch.setattr(desktop, "window_text", lambda t, limit=4000: {"marker": "read"})

    assert desktop.dispatch("windows")["marker"] == "windows"
    assert desktop.dispatch("focus", title="Notepad")["title"] == "Notepad"
    assert desktop.dispatch("type", keys="hello")["keys"] == "hello"
    assert desktop.dispatch("read", window="Notepad")["marker"] == "read"
    assert desktop.dispatch("ui")["platform"]
    assert desktop.dispatch("hud")["ok"] is True


def test_window_alias_works_like_title(monkeypatch):
    monkeypatch.setattr(desktop, "focus_window", lambda t: {"ok": True, "got": t})
    assert desktop.dispatch("focus", window="Chrome")["got"] == "Chrome"


def test_browser_farm_refusal_survives_the_new_actions():
    """The new UI control must not become a back door to the thing that stays refused."""
    out = desktop.dispatch("comment")
    assert out.get("blocked") is True
