"""The browser half of the diagnosis.

/api/health/full and /api/voice/selftest both came back clean while the HUD still said
nothing, because the remaining failures live in the browser and the server cannot see
them: a stale token in localStorage, a suspended AudioContext, a refused microphone, a
stream that closes without an event. This page has to be reachable exactly when the HUD
is not working, which means no token.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app import main as main_mod  # noqa: E402

client = TestClient(main_mod.app, base_url="http://127.0.0.1")
PAGE = (ROOT / "web" / "diag.html").read_text(encoding="utf-8")


def test_the_page_is_open():
    """It is for when the HUD cannot hand you a token. Guarding it defeats the point."""
    assert "/diag" in main_mod._OPEN_PATHS
    assert client.get("/diag").status_code == 200


def test_it_serves_html():
    resp = client.get("/diag")
    assert "text/html" in resp.headers["content-type"]
    assert "<title>Jarvis diagnostics</title>" in resp.text


def test_it_covers_every_link_in_the_chain():
    for probe in ("checkBootstrap", "checkHealth", "checkChat", "checkStream", "checkSocket", "checkMic", "checkAudio"):
        assert f"function {probe}" in PAGE or f"async function {probe}" in PAGE, f"{probe} missing"


def test_it_calls_out_a_stale_token_by_name():
    """A stale localStorage token breaks every call and looks like a dead backend."""
    assert "STALE" in PAGE


def test_it_names_the_4401_rejection():
    assert "4401" in PAGE


def test_the_socket_check_cannot_hang_forever():
    """A probe that never resolves is worse than one that fails."""
    assert "setTimeout" in PAGE and "15000" in PAGE


def test_it_produces_something_copyable():
    """The whole point is one paste, not a screenshot of a console."""
    assert "function summarise" in PAGE
    assert 'getElementById("out")' in PAGE


def test_the_page_is_self_contained():
    """It has to work when the app's own assets or network are the problem."""
    for offender in ("src=\"http", "href=\"http", "cdn.", "unpkg", "googleapis"):
        assert offender not in PAGE, f"{offender} would make the diagnostic depend on the network"
