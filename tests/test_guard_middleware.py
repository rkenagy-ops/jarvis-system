"""The lock message must be actionable.

"jarvis locked" alone sent a real debugging session hunting for a crash that was not
there — the endpoint simply predated the running process. The 401 now has to say what
is missing, how to get it, and that a stale process is a possible cause.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app import main as main_mod  # noqa: E402

# The fortress rejects any Host it does not recognise, and TestClient defaults to
# "testserver". Pin it to loopback so these exercise the token check rather than
# bouncing off host_ok first.
client = TestClient(main_mod.app, base_url="http://127.0.0.1")


def test_open_paths_need_no_token():
    for path in ("/api/health", "/api/health/full"):
        assert client.get(path).status_code == 200, f"{path} should be open"


def test_health_full_is_open_because_chat_may_be_down():
    """The deep check exists for when the brain is degraded — the moment the HUD
    chat cannot be used to ask why. It has to work without it."""
    assert "/api/health/full" in main_mod._OPEN_PATHS
    body = client.get("/api/health/full").json()
    assert "verdict" in body and "brain" in body and "voice" in body


def test_locked_response_explains_itself():
    resp = client.get("/api/markets")
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"] == "jarvis locked"
    assert body["reason"]
    assert body["how_to_unlock"]
    assert any("token" in step.lower() for step in body["how_to_unlock"])


def test_locked_response_lists_open_paths():
    body = client.get("/api/markets").json()
    assert "/api/health" in body["open_paths"]
    assert "/api/health/full" in body["open_paths"]


def test_unknown_path_hints_at_a_stale_process():
    """The actual failure: the endpoint existed in the repo but not in the process."""
    body = client.get("/api/some-endpoint-added-later").json()
    assert "not a route on this build" in body["reason"]
    assert "git pull and restart" in body["hint"]


def test_known_but_guarded_path_does_not_blame_staleness():
    """A genuinely token-protected endpoint should not send you chasing a pull."""
    body = client.get("/api/markets").json()
    assert body["hint"] is None
    assert "needs the fortress token" in body["reason"]


def test_parameterised_routes_count_as_known():
    """/api/thing/{id} exists on this build even though no literal path matches it."""
    import re

    from app import main as m

    parameterised = [
        r.path for r in m.app.routes if "{" in getattr(r, "path", "") and r.path.startswith("/api/")
    ]
    if not parameterised:
        return
    concrete = re.sub(r"\{[^}]+\}", "probe", parameterised[0])
    body = client.get(concrete).json()
    assert body["hint"] is None, f"{concrete} exists on this build; do not blame staleness"


def test_the_token_is_never_echoed():
    body = client.get("/api/markets").text
    from app import guard

    token = guard.token()
    assert token and token not in body, "the 401 must not leak the token it is asking for"


def test_a_valid_token_unlocks():
    from app import guard

    resp = client.get("/api/markets", headers={"x-jarvis-token": guard.token()})
    assert resp.status_code != 401


def test_query_param_token_also_works():
    from app import guard

    resp = client.get(f"/api/markets?token={guard.token()}")
    assert resp.status_code != 401


def test_voice_selftest_is_open_because_voice_is_the_broken_thing():
    """You reach for this when voice is down; it must not need the HUD to hand you a token."""
    assert "/api/voice/selftest" in main_mod._OPEN_PATHS
    body = client.get("/api/voice/selftest").json()
    assert "ok" in body and "stage" in body


def test_selftest_reports_a_stage_so_you_know_how_far_it_got():
    """config / import / connect / session are four different problems."""
    body = client.get("/api/voice/selftest").json()
    assert body["stage"] in {"config", "import", "connect", "session"}
    if not body["ok"]:
        assert body.get("error"), "a failure has to say what failed"


def test_a_mistyped_path_suggests_the_real_one():
    """A missing letter sent a real session chasing a git pull. Check the near miss first."""
    body = client.get("/api/voice/selftes").json()
    assert "/api/voice/selftest" in body["hint"]
    assert "git pull" not in body["hint"], "a typo is not a stale process"


def test_a_genuinely_unknown_path_still_blames_staleness():
    """The near-miss check must not swallow the case it was built around."""
    body = client.get("/api/nothing-remotely-like-a-route-here").json()
    assert "git pull and restart" in body["hint"]


def test_a_trailing_slash_is_the_same_endpoint():
    """FastAPI would redirect it, but the guard runs before routing - so the slash
    version was refused as unknown and the 401 sent the user off to git pull."""
    for path in ("/api/voice/log/", "/api/health/full/", "/diag/"):
        assert client.get(path).status_code == 200, f"{path} should behave like {path[:-1]}"


def test_a_trailing_slash_on_a_guarded_route_is_still_guarded():
    """Normalising the slash must not become a way around the token."""
    resp = client.get("/api/markets/")
    assert resp.status_code == 401
    assert resp.json()["hint"] is None, "it exists on this build; do not blame staleness"


def test_the_root_path_survives_normalisation():
    """"/" is one character of trailing slash and must not be stripped to nothing."""
    assert main_mod._canonical("/") == "/"
    assert client.get("/").status_code == 200
