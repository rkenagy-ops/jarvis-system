from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import agents, memory, tools


def test_agents_present():
    ids = set(agents.AGENTS)
    assert len(ids) == 15
    assert {"jarvis", "scribe", "social", "merch", "publisher", "scheduler", "designer"} <= ids
    assert agents.get("jarvis").can_spawn
    assert not agents.get("oracle").can_spawn


def test_tools_for_jarvis_includes_spawn_and_github():
    names = {t.get("name") or t.get("type") for t in tools.tools_for("jarvis", allow_spawn=True)}
    assert "web_search" in names
    assert "x_search" in names
    assert "spawn_agents" in names
    assert "github" in names


def test_tools_for_specialist_no_spawn():
    names = {t.get("name") or t.get("type") for t in tools.tools_for("oracle", allow_spawn=False)}
    assert "spawn_agents" not in names
    assert "github" not in names
    assert "web_search" in names


def test_fetch_url_rejects_bad_scheme():
    assert "error" in tools.fetch_url("file:///etc/passwd")
    assert "error" in tools.fetch_url("not-a-url")


def test_memory_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "t.db")
    memory.init()
    memory.remember("Owner prefers concise briefings", kind="preference", tags=["owner"], importance=0.9)
    memory.set_fact("owner.name", "Rhett", confidence=0.99)
    hits = memory.search("concise")
    assert hits
    assert any("concise" in h["content"] for h in hits)
    facts = {f["key"]: f["value"] for f in memory.get_facts()}
    assert facts["owner.name"] == "Rhett"
    snap = memory.snapshot("s1")
    assert "unlocked" in snap.lower()
    assert "Rhett" in snap
