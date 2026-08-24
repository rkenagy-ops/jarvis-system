from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import learning, repo_index


def test_entries_are_well_formed():
    for e in repo_index.INDEX:
        assert set(e) >= {"repo", "category", "priority", "why"}
        assert "/" in e["repo"] and e["repo"].count("/") == 1
        assert e["priority"] in (1, 2, 3)
        assert len(e["why"]) > 20, f"{e['repo']} needs a real reason"


def test_hubs_are_well_formed():
    for h in repo_index.HUBS:
        assert h["repo"].count("/") == 1
        assert h["why"]


def test_no_duplicate_repos():
    repos = repo_index.all_repos()
    assert len(repos) == len(set(repos))


def test_every_repo_passes_oss_validation():
    """An index entry that oss.fetch would reject is dead weight."""
    from app import oss

    for repo in repo_index.all_repos():
        assert oss._valid(repo), f"{repo} would be rejected by oss.fetch"


def test_categories_line_up_with_learning_topics():
    """A category with no matching topic never gets picked up by a cycle."""
    orphans = set(repo_index.categories()) - set(learning.TOPICS)
    assert not orphans, f"index categories with no learning topic: {sorted(orphans)}"


def test_every_topic_has_indexed_repos():
    """The reverse direction, and the one that was actually broken: a topic with no
    indexed repo falls back to GitHub search, which needs a token — so with no token
    that topic silently contributes nothing to a cycle."""
    empty = set(learning.TOPICS) - set(repo_index.categories())
    assert not empty, f"topics with no indexed repos (search-only): {sorted(empty)}"


def test_for_topic_sorts_by_priority():
    rows = repo_index.for_topic("trading")
    assert rows
    assert [r["priority"] for r in rows] == sorted(r["priority"] for r in rows)


def test_for_topic_unknown_is_empty():
    assert repo_index.for_topic("nonsense") == []


def test_ib_async_is_indexed_first():
    """ib_insync is archived — the maintained fork should be priority 1."""
    trading = repo_index.for_topic("trading")
    assert trading[0]["repo"] == "ib-api-reloaded/ib_async"


def test_summary_shape():
    s = repo_index.summary()
    assert s["ok"] and s["total_repos"] == len(repo_index.all_repos())
    assert s["priority_1"]
