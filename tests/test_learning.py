from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import learning


def test_topics_are_real_queries():
    for topic, query in learning.TOPICS.items():
        assert topic.islower() and " " not in topic
        assert len(query) > 5


def test_ledger_roundtrip(monkeypatch):
    store = {}
    monkeypatch.setattr(learning.memory, "get_facts", lambda: [{"key": k, "value": v} for k, v in store.items()])
    monkeypatch.setattr(
        learning.memory, "set_fact", lambda k, v, **kw: store.__setitem__(k, v)
    )
    assert learning._ledger() == []
    learning._remember_repo("a/b")
    assert learning._ledger() == ["a/b"]
    # idempotent
    learning._remember_repo("a/b")
    assert learning._ledger() == ["a/b"]
    learning._remember_repo("c/d")
    assert learning._ledger() == ["a/b", "c/d"]


def test_candidates_skip_already_learned(monkeypatch):
    monkeypatch.setattr(learning, "_ledger", lambda: ["old/repo"])
    monkeypatch.setattr(
        learning.oss,
        "search",
        lambda q, limit=10: {
            "ok": True,
            "repos": [{"repo": "old/repo", "stars": 9}, {"repo": "new/repo", "stars": 5}],
        },
    )
    out = learning.candidates("agents", limit=5)
    assert out["ok"]
    assert [c["repo"] for c in out["candidates"]] == ["new/repo"]


def test_candidates_propagates_search_failure(monkeypatch):
    monkeypatch.setattr(learning.oss, "search", lambda q, limit=10: {"error": "rate limited"})
    assert "error" in learning.candidates("agents")


def test_study_validates_repo():
    assert "error" in learning.study("not-a-repo")
    assert "error" in learning.study("../evil")


def test_study_fetches_ingests_and_records(monkeypatch):
    recorded = []
    monkeypatch.setattr(learning.oss, "fetch", lambda r: {"ok": True, "files": 120})
    monkeypatch.setattr(
        learning.oss, "ingest", lambda r, max_files=30: {"ok": True, "files_ingested": 25, "vault": "Sources/oss/x.md"}
    )
    monkeypatch.setattr(learning, "_remember_repo", lambda r: recorded.append(r))
    monkeypatch.setattr(learning.memory, "remember", lambda *a, **k: None)

    out = learning.study("pola-rs/polars")
    assert out["ok"] is True
    assert out["files_ingested"] == 25
    assert recorded == ["pola-rs/polars"]


def test_study_stops_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(learning.oss, "fetch", lambda r: {"error": "404"})

    def should_not_run(*a, **k):
        raise AssertionError("must not ingest when fetch failed")

    monkeypatch.setattr(learning.oss, "ingest", should_not_run)
    assert "error" in learning.study("a/b")


def test_cycle_is_bounded_and_broad(monkeypatch):
    """One repo per topic per cycle, capped by max_repos."""
    studied = []
    monkeypatch.setattr(learning, "_ledger", lambda: [])
    monkeypatch.setattr(
        learning,
        "candidates",
        lambda topic, limit=3: {
            "ok": True,
            "candidates": [{"repo": f"{topic}/one", "stars": 1}, {"repo": f"{topic}/two", "stars": 2}],
        },
    )

    def fake_study(repo, **kw):
        studied.append(repo)
        return {"ok": True, "repo": repo, "files_ingested": 3, "vault": "v"}

    monkeypatch.setattr(learning, "study", fake_study)
    out = learning.cycle(max_repos=2, reindex=False)
    assert out["ok"]
    assert len(studied) == 2
    # different topics, not two from the same one
    assert len({r.split("/")[0] for r in studied}) == 2


def test_cycle_reports_when_nothing_new(monkeypatch):
    monkeypatch.setattr(learning, "_ledger", lambda: ["a/b"])
    monkeypatch.setattr(learning, "candidates", lambda topic, limit=3: {"ok": True, "candidates": []})
    out = learning.cycle(reindex=False)
    assert out["studied"] == []
    assert "Nothing new" in out["summary"]
    assert len(out["skipped"]) == len(learning.TOPICS)


def test_cycle_survives_reindex_failure(monkeypatch):
    monkeypatch.setattr(learning, "_ledger", lambda: [])
    monkeypatch.setattr(
        learning, "candidates", lambda topic, limit=3: {"ok": True, "candidates": [{"repo": "a/b"}]}
    )
    monkeypatch.setattr(
        learning, "study", lambda repo, **kw: {"ok": True, "repo": repo, "files_ingested": 1, "vault": "v"}
    )
    # `from . import rag` resolves the attribute already bound on the app package,
    # so patching sys.modules is order-dependent — patch the function itself.
    from app import rag as rag_mod

    def boom():
        raise RuntimeError("ollama down")

    monkeypatch.setattr(rag_mod, "reindex_vault", boom)
    out = learning.cycle(max_repos=1, reindex=True)
    assert out["ok"] is True
    assert "reindex failed" in str(out["reindexed"])


def test_cycle_accepts_topic_string(monkeypatch):
    seen = []
    monkeypatch.setattr(learning, "_ledger", lambda: [])
    monkeypatch.setattr(
        learning,
        "candidates",
        lambda topic, limit=3: seen.append(topic) or {"ok": True, "candidates": []},
    )
    learning.cycle(topics="trading,agents", reindex=False)
    assert seen == ["trading", "agents"]


def test_dispatch_routes():
    assert "error" in learning.dispatch("bogus")
    assert "actions" in learning.dispatch("bogus")
