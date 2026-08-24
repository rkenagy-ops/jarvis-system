from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import bots, stack, tools


def test_refuse_hamburger():
    out = stack.refuse_browser_farm()
    assert out.get("blocked") is True
    assert "hamburger" in out["reason"].lower()
    # A bare "comment" ask is still the feed-farming ask -> refused.
    assert stack.dispatch("comment").get("blocked") is True
    assert stack.dispatch("hamburger").get("blocked") is True
    assert stack.dispatch("switch_account").get("blocked") is True
    assert stack.dispatch("feed").get("blocked") is True


def test_refuse_comment_on_someone_elses_post():
    out = stack.dispatch(
        "comment",
        account_id="abc",
        text="hi",
        comment="nice post",
        url="https://www.instagram.com/p/Cxyz123/",
    )
    assert out.get("blocked") is True
    assert "farming" in out["reason"].lower()


def test_normalize_comments_shapes():
    got, err = stack._normalize_comments("first!")
    assert err is None
    assert got == [{"text": "first!"}]

    got, err = stack._normalize_comments(["a", "b"], delay=5)
    assert err is None
    assert got == [
        {"text": "a", "delay": {"duration": 5, "unit": "Minute"}},
        {"text": "b", "delay": {"duration": 5, "unit": "Minute"}},
    ]

    got, err = stack._normalize_comments([{"text": "x", "delay": {"duration": 2, "unit": "Hour"}}])
    assert err is None
    assert got[0]["delay"] == {"duration": 2, "unit": "Hour"}

    # per-item delay wins over the default
    got, err = stack._normalize_comments([{"text": "x", "delay": 9}], delay=1)
    assert err is None
    assert got[0]["delay"] == {"duration": 9, "unit": "Minute"}

    assert stack._normalize_comments([{"text": "  "}])[1]
    assert stack._normalize_comments(["ok"] * (stack.MAX_COMMENTS + 1))[1]
    assert stack._normalize_comments(None) == ([], None)

    # only whitelisted keys reach Publer
    got, err = stack._normalize_comments([{"text": "x", "evil": "drop me"}])
    assert err is None and "evil" not in got[0]


def test_comment_rejects_unsupported_network():
    out = stack.publer_schedule(text="hi", account_id="abc", network="tiktok", comments="first!")
    assert "error" in out
    assert "tiktok" in out["error"]


def test_comment_needs_confirm_and_carries_comments(monkeypatch):
    captured = {}

    def fake_create_pending(kind, payload, ttl_sec=300):
        captured["kind"] = kind
        captured["payload"] = payload
        return {"confirm_token": "tok", "kind": kind}

    monkeypatch.setattr(stack, "publer_ready", lambda: True)
    monkeypatch.setattr(stack.config, "PUBLER_API_KEY", "x")
    monkeypatch.setattr(stack.config, "PUBLER_WORKSPACE_ID", "ws")
    monkeypatch.setattr(stack.memory, "create_pending", fake_create_pending)

    out = stack.dispatch(
        "comment",
        account_id="abc",
        text="post body",
        comment="first comment #tags",
        network="instagram",
        when="2026-09-01T12:00:00Z",
        comment_delay=3,
    )
    assert out.get("blocked") is True
    assert out.get("confirm_token") == "tok"
    assert captured["kind"] == "publer_post"
    assert captured["payload"]["comments"] == [
        {"text": "first comment #tags", "delay": {"duration": 3, "unit": "Minute"}}
    ]


def test_confirmed_comment_hits_publer_payload(monkeypatch):
    sent = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"job_id": "job-1"}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None):
            sent["url"] = url
            sent["body"] = json
            return FakeResponse()

    monkeypatch.setattr(stack, "publer_ready", lambda: True)
    monkeypatch.setattr(stack.config, "PUBLER_API_KEY", "x")
    monkeypatch.setattr(stack.config, "PUBLER_WORKSPACE_ID", "ws")
    monkeypatch.setattr(stack.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        stack.memory,
        "consume_pending",
        lambda tok: {
            "kind": "publer_post",
            "payload": {
                "text": "post body",
                "account_id": "abc",
                "network": "instagram",
                "when": "2026-09-01T12:00:00Z",
                "live": False,
                "comments": [{"text": "first comment"}],
            },
        },
    )

    out = stack.dispatch(
        "comment",
        account_id="abc",
        text="post body",
        comment="first comment",
        network="instagram",
        when="2026-09-01T12:00:00Z",
        confirm_token="tok",
    )
    assert out.get("ok") is True
    assert out.get("job_id") == "job-1"
    assert out.get("comments") == 1
    account = sent["body"]["bulk"]["posts"][0]["accounts"][0]
    assert account["comments"] == [{"text": "first comment"}]
    assert "instagram" in sent["body"]["bulk"]["posts"][0]["networks"]


def test_confirmed_payload_overrides_caller_supplied_comment(monkeypatch):
    """A caller cannot swap the comment text after the user approved it."""

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"job_id": "job-2"}

    sent = {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None):
            sent["body"] = json
            return FakeResponse()

    monkeypatch.setattr(stack, "publer_ready", lambda: True)
    monkeypatch.setattr(stack.config, "PUBLER_API_KEY", "x")
    monkeypatch.setattr(stack.config, "PUBLER_WORKSPACE_ID", "ws")
    monkeypatch.setattr(stack.httpx, "Client", FakeClient)
    monkeypatch.setattr(
        stack.memory,
        "consume_pending",
        lambda tok: {
            "kind": "publer_post",
            "payload": {
                "text": "approved body",
                "account_id": "abc",
                "network": "facebook",
                "when": "2026-09-01T12:00:00Z",
                "live": False,
                "comments": [{"text": "APPROVED"}],
            },
        },
    )

    stack.publer_schedule(
        text="approved body",
        account_id="abc",
        network="facebook",
        when="2026-09-01T12:00:00Z",
        confirm_token="tok",
        comments="SNEAKY",
    )
    assert sent["body"]["bulk"]["posts"][0]["accounts"][0]["comments"] == [{"text": "APPROVED"}]


def test_status_without_keys():
    st = stack.status()
    assert "publer" in st
    assert st.get("refused")


def test_publer_schedule_needs_confirm(monkeypatch):
    monkeypatch.setattr(stack, "publer_ready", lambda: True)
    monkeypatch.setattr(stack.config, "PUBLER_API_KEY", "x")
    monkeypatch.setattr(stack.config, "PUBLER_WORKSPACE_ID", "ws")
    monkeypatch.setattr(
        stack.memory,
        "create_pending",
        lambda *a, **k: {"confirm_token": "tok", "kind": "publer_post"},
    )
    out = stack.publer_schedule(text="hi", account_id="abc", when="2026-09-01T12:00:00Z", live=False)
    assert out.get("blocked") is True
    assert out.get("confirm_token") == "tok"


def test_bot_roster():
    assert len(bots.SPECS) == 21
    names = [s[0] for s in bots.SPECS]
    assert names[0].startswith("bot-01")
    assert names[-1].startswith("bot-21")
    assert len(set(names)) == 21


def test_stack_tool_on_jarvis():
    names = {t.get("name") or t.get("type") for t in tools.tools_for("jarvis", allow_spawn=True)}
    assert "stack" in names


def test_new_tools_are_registered():
    jarvis = {t.get("name") or t.get("type") for t in tools.tools_for("jarvis", allow_spawn=True)}
    for name in ("stack", "engage", "oss", "setups", "market"):
        assert name in jarvis, f"{name} missing from jarvis toolset"


def test_oss_is_ungated():
    """Unrestricted access means every agent can reach it."""
    for agent in ("jarvis", "scribe", "analyst", "trader", "designer"):
        names = {t.get("name") or t.get("type") for t in tools.tools_for(agent, allow_spawn=False)}
        assert "oss" in names, f"oss missing for {agent}"


def test_setups_follows_market_gating():
    scribe = {t.get("name") or t.get("type") for t in tools.tools_for("scribe", allow_spawn=False)}
    assert ("setups" in scribe) == ("market" in scribe)


def test_engage_follows_stack_gating():
    for agent in ("jarvis", "social", "scribe", "analyst"):
        names = {t.get("name") or t.get("type") for t in tools.tools_for(agent, allow_spawn=False)}
        assert ("engage" in names) == ("stack" in names), f"engage/stack gating diverged for {agent}"
