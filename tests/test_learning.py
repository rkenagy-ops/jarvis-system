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
    """Search results already in the ledger are dropped (index entries too)."""
    monkeypatch.setattr(learning, "_ledger", lambda: ["old/repo"])
    monkeypatch.setattr(learning, "search_available", lambda: True)
    monkeypatch.setattr(
        learning,
        "repo_index",
        type("Stub", (), {"for_topic": staticmethod(lambda t: []), "HUBS": []})(),
    )
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


def test_search_failure_no_longer_kills_discovery(monkeypatch):
    """Previously a search error was returned as the whole result, so a missing
    token meant zero candidates. The index must now carry the cycle regardless."""
    monkeypatch.setattr(learning, "_ledger", lambda: [])
    monkeypatch.setattr(learning, "search_available", lambda: True)
    monkeypatch.setattr(learning.oss, "search", lambda q, limit=10: {"error": "rate limited"})
    # limit above the index count, so search is actually attempted and fails
    out = learning.candidates("agents", limit=20)
    assert out["ok"] is True
    assert "error" not in out
    assert out["candidates"], "index must still produce candidates"
    assert out["search_error"] == "rate limited"


def test_search_skipped_when_index_fills_the_quota(monkeypatch):
    """No point spending an authenticated API call the index already covered."""
    monkeypatch.setattr(learning, "_ledger", lambda: [])
    monkeypatch.setattr(learning, "search_available", lambda: True)

    def must_not_search(*a, **k):
        raise AssertionError("search should be skipped when the index already fills the limit")

    monkeypatch.setattr(learning.oss, "search", must_not_search)
    out = learning.candidates("agents", limit=1)
    assert len(out["candidates"]) == 1
    assert out["searched"] is False


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


# --- index-first discovery ---------------------------------------------------


def test_candidates_work_without_a_github_token(monkeypatch):
    """The original bug: no token meant no discovery at all."""
    monkeypatch.setattr(learning, "_ledger", lambda: [])
    monkeypatch.setattr(learning, "search_available", lambda: False)

    def must_not_search(*a, **k):
        raise AssertionError("should not call GitHub search without a token")

    monkeypatch.setattr(learning.oss, "search", must_not_search)

    out = learning.candidates("trading", limit=5)
    assert out["ok"] is True
    assert out["candidates"], "index must supply candidates with no credentials"
    assert out["index_only"] is True
    assert all(c["source"] == "index" for c in out["candidates"])


def test_candidates_layer_search_on_top_when_token_present(monkeypatch):
    monkeypatch.setattr(learning, "_ledger", lambda: [])
    monkeypatch.setattr(learning, "search_available", lambda: True)
    monkeypatch.setattr(
        learning.oss,
        "search",
        lambda q, limit=10: {"ok": True, "repos": [{"repo": "extra/found", "stars": 10}]},
    )
    out = learning.candidates("trading", limit=20)
    sources = {c["source"] for c in out["candidates"]}
    assert sources == {"index", "search"}
    assert out["searched"] is True
    # indexed repos still rank ahead of search results
    assert out["candidates"][0]["source"] == "index"


def test_candidates_survive_search_failure(monkeypatch):
    monkeypatch.setattr(learning, "_ledger", lambda: [])
    monkeypatch.setattr(learning, "search_available", lambda: True)
    monkeypatch.setattr(learning.oss, "search", lambda q, limit=10: {"error": "rate limited"})
    out = learning.candidates("trading", limit=5)
    assert out["ok"] is True
    assert out["candidates"], "index results must survive a search failure"
    assert out["search_error"] == "rate limited"


def test_candidates_skip_studied_index_entries(monkeypatch):
    from app import repo_index

    first = repo_index.for_topic("trading")[0]["repo"]
    monkeypatch.setattr(learning, "_ledger", lambda: [first])
    monkeypatch.setattr(learning, "search_available", lambda: False)
    out = learning.candidates("trading", limit=5)
    assert first not in [c["repo"] for c in out["candidates"]]


def test_cycle_reports_discovery_mode(monkeypatch):
    monkeypatch.setattr(learning, "_ledger", lambda: [])
    monkeypatch.setattr(learning, "search_available", lambda: False)
    monkeypatch.setattr(learning, "candidates", lambda topic, limit=3: {"ok": True, "candidates": []})
    out = learning.cycle(reindex=False)
    assert out["search_enabled"] is False
    assert out["discovery"] == "curated index only"


def test_index_action_flags_missing_token(monkeypatch):
    monkeypatch.setattr(learning, "_ledger", lambda: [])
    monkeypatch.setattr(learning, "search_available", lambda: False)
    out = learning.index()
    assert out["search_enabled"] is False
    assert "search_note" in out
    assert out["unstudied"]


def test_hubs_ingest_awesome_lists(monkeypatch):
    from app import repo_index

    done = []
    monkeypatch.setattr(learning, "_ledger", lambda: [])
    monkeypatch.setattr(
        learning,
        "study",
        lambda repo, max_files=8: done.append(repo) or {"ok": True, "repo": repo, "files_ingested": 5},
    )
    out = learning.hubs(max_repos=2)
    assert out["ok"] and len(out["hubs"]) == 2
    assert done[0] == repo_index.HUBS[0]["repo"]


def test_dispatch_exposes_index_and_hubs():
    actions = learning.dispatch("bogus")["actions"]
    assert "index" in actions and "hubs" in actions
