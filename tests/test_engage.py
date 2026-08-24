from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import engage


def test_meta_networks_are_never_auto():
    """Instagram/Facebook have no comment-on-others endpoint. This must not regress."""
    caps = engage.capabilities()
    for network in ("instagram", "facebook"):
        assert caps[network]["auto"] is False
        assert caps[network]["official"] is False
    assert "instagram" not in engage.AUTO_NETWORKS
    assert "facebook" not in engage.AUTO_NETWORKS
    assert engage.REVIEW_NETWORKS == {"instagram", "facebook"}
    # and there is no replier wired up for them at all
    assert set(engage.REPLIERS) == {"x", "threads", "linkedin"}


def test_generic_comment_detection():
    assert engage._is_generic("Great post! Thanks.")
    assert engage._is_generic("love this")
    assert engage._is_generic("Thanks for sharing 🙏")
    assert not engage._is_generic("The 30% figure tracks with what we saw in Q2 — was that gross or net?")


def test_freshness_window():
    import time

    assert engage._fresh(None) is True
    assert engage._fresh(time.time() - 60) is True
    assert engage._fresh(time.time() - engage.MAX_POST_AGE_SEC - 60) is False


def test_iso_parsing():
    assert engage._iso_to_epoch("2026-08-24T10:00:00Z") > 0
    assert engage._iso_to_epoch(None) is None
    assert engage._iso_to_epoch("not-a-date") is None


def test_select_skips_engaged_stale_and_empty(monkeypatch):
    import time

    now = time.time()
    posts = [
        {"id": "1", "text": "fresh and good", "score": 5, "created_at": now},
        {"id": "2", "text": "already done", "score": 99, "created_at": now},
        {"id": "3", "text": "", "score": 50, "created_at": now},
        {"id": "4", "text": "too old", "score": 80, "created_at": now - engage.MAX_POST_AGE_SEC - 10},
        {"id": "5", "text": "also fresh", "score": 9, "created_at": now},
    ]
    monkeypatch.setattr(engage.memory, "already_engaged", lambda net, pid: pid == "2")

    picked = engage._select(posts, "x", 5)
    ids = [p["id"] for p in picked]
    assert ids == ["5", "1"]  # score-ordered, 2/3/4 filtered out


def test_draft_rejects_generic(monkeypatch):
    monkeypatch.setattr(engage.brain, "think", lambda *a, **k: {"text": "Great post! So true."})
    out = engage.draft_comment({"text": "some post", "network": "x", "author": "a"})
    assert out["ok"] is False
    assert out["skip"] is True


def test_draft_honours_skip(monkeypatch):
    monkeypatch.setattr(engage.brain, "think", lambda *a, **k: {"text": "SKIP"})
    out = engage.draft_comment({"text": "some post", "network": "x", "author": "a"})
    assert out["ok"] is False and out["skip"] is True


def test_draft_accepts_specific(monkeypatch):
    good = "The 30% figure tracks with what we saw last quarter - was that gross or net of churn?"
    monkeypatch.setattr(engage.brain, "think", lambda *a, **k: {"text": good})
    out = engage.draft_comment({"text": "some post", "network": "x", "author": "a"})
    assert out["ok"] is True
    assert out["comment"] == good


def test_run_queues_instagram_never_posts(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        engage,
        "discover_instagram",
        lambda limit=10, topics=None: {
            "ok": True,
            "posts": [
                {
                    "network": "instagram",
                    "id": "ig1",
                    "text": "a real post about supply chains",
                    "score": 10,
                    "created_at": None,
                    "permalink": "https://instagram.com/p/ig1",
                }
            ],
        },
    )
    monkeypatch.setitem(engage.DISCOVERY, "instagram", engage.discover_instagram)
    monkeypatch.setattr(engage.memory, "already_engaged", lambda *a: False)
    monkeypatch.setattr(engage.memory, "engagements_since", lambda s: [])
    monkeypatch.setattr(
        engage.memory,
        "record_engagement",
        lambda net, pid, **kw: recorded.append((net, pid, kw.get("status"))),
    )
    monkeypatch.setattr(
        engage.brain,
        "think",
        lambda *a, **k: {"text": "Curious how you handled the port delays - did you re-route or eat the lead time?"},
    )

    out = engage.run(networks="instagram", per_network=1)
    assert out["posted"] == []
    assert len(out["queued_for_review"]) == 1
    assert out["queued_for_review"][0]["network"] == "instagram"
    assert recorded == [("instagram", "ig1", "queued")]


def test_run_posts_on_x_when_official(monkeypatch):
    sent = []
    monkeypatch.setattr(
        engage,
        "discover_x",
        lambda limit=10: {
            "ok": True,
            "posts": [
                {
                    "network": "x",
                    "id": "t1",
                    "text": "shipping costs are up again",
                    "score": 10,
                    "created_at": None,
                    "permalink": "https://x.com/a/status/t1",
                }
            ],
        },
    )
    monkeypatch.setitem(engage.DISCOVERY, "x", engage.discover_x)
    monkeypatch.setattr(engage, "capabilities", lambda: {"x": {"auto": True, "official": True, "reason": None}})
    monkeypatch.setattr(engage.memory, "already_engaged", lambda *a: False)
    monkeypatch.setattr(engage.memory, "engagements_since", lambda s: [])
    monkeypatch.setattr(engage.memory, "record_engagement", lambda *a, **k: None)
    monkeypatch.setattr(
        engage.brain,
        "think",
        lambda *a, **k: {"text": "Are you seeing that on trans-pacific specifically, or across all lanes?"},
    )
    monkeypatch.setitem(
        engage.REPLIERS, "x", lambda pid, text: (sent.append((pid, text)), {"ok": True, "data": {}})[1]
    )

    out = engage.run(networks="x", per_network=1)
    assert len(out["posted"]) == 1
    assert sent and sent[0][0] == "t1"


def test_dry_run_posts_nothing(monkeypatch):
    monkeypatch.setattr(
        engage,
        "discover_x",
        lambda limit=10: {
            "ok": True,
            "posts": [
                {"network": "x", "id": "t9", "text": "a post", "score": 1, "created_at": None, "permalink": "p"}
            ],
        },
    )
    monkeypatch.setitem(engage.DISCOVERY, "x", engage.discover_x)
    monkeypatch.setattr(engage, "capabilities", lambda: {"x": {"auto": True, "official": True, "reason": None}})
    monkeypatch.setattr(engage.memory, "already_engaged", lambda *a: False)
    monkeypatch.setattr(engage.memory, "engagements_since", lambda s: [])
    monkeypatch.setattr(engage.memory, "record_engagement", lambda *a, **k: None)
    monkeypatch.setattr(engage.brain, "think", lambda *a, **k: {"text": "A specific and useful question about it?"})

    def boom(*a, **k):
        raise AssertionError("dry_run must not post")

    monkeypatch.setitem(engage.REPLIERS, "x", boom)
    out = engage.run(networks="x", per_network=1, dry_run=True)
    assert out["posted"] == []
    assert out["networks"]["x"]["results"][0]["would_post"] is True


def test_daily_cap_blocks_posting(monkeypatch):
    monkeypatch.setattr(
        engage,
        "discover_x",
        lambda limit=10: {
            "ok": True,
            "posts": [
                {"network": "x", "id": "t5", "text": "a post", "score": 1, "created_at": None, "permalink": "p"}
            ],
        },
    )
    monkeypatch.setitem(engage.DISCOVERY, "x", engage.discover_x)
    monkeypatch.setattr(engage, "capabilities", lambda: {"x": {"auto": True, "official": True, "reason": None}})
    monkeypatch.setattr(engage.memory, "already_engaged", lambda *a: False)
    # already at the cap today
    monkeypatch.setattr(
        engage.memory,
        "engagements_since",
        lambda s: [{"status": "posted"}] * (engage.config.ENGAGE_DAILY_CAP or 15),
    )
    monkeypatch.setattr(engage.memory, "record_engagement", lambda *a, **k: None)
    monkeypatch.setattr(engage.brain, "think", lambda *a, **k: {"text": "A specific and useful question about it?"})

    def boom(*a, **k):
        raise AssertionError("cap must block posting")

    monkeypatch.setitem(engage.REPLIERS, "x", boom)
    out = engage.run(networks="x", per_network=1)
    assert out["posted"] == []
    assert out["daily_cap_remaining"] == 0


def test_per_network_is_clamped(monkeypatch):
    monkeypatch.setattr(engage.memory, "engagements_since", lambda s: [])
    out = engage.run(networks="nonsense", per_network=999)
    assert out["unknown_networks"] == ["nonsense"]


def test_dispatch_unknown_action():
    assert "error" in engage.dispatch("nope")
