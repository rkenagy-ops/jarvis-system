from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import meetings, obsidian


SAMPLE = """Title: Pipeline sync
Attendees: Rhett, Sam
We talked through the midstream deck.
Decision: ship the WordPress draft as-is
Action: Rhett send the deck today
TODO: Sam review comments
"""


def test_parse_extracts():
    out = meetings.parse(SAMPLE)
    assert out["title"] == "Pipeline sync"
    assert "Rhett" in out["attendees"]
    assert any("WordPress" in d for d in out["decisions"])
    assert any("deck" in a.lower() for a in out["actions"])
    assert any("review" in a.lower() for a in out["actions"])


def test_file_minutes_writes_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(obsidian.config, "VAULT_DIR", tmp_path / "vault")
    monkeypatch.setattr(meetings.memory, "remember", lambda *a, **k: None)
    out = meetings.file_minutes(SAMPLE)
    assert out["ok"]
    path = tmp_path / "vault" / out["path"]
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "- [ ] Rhett send the deck today" in text
    tasks = obsidian.list_tasks(open_only=True)
    assert any("deck" in t["text"].lower() for t in tasks)
    listed = meetings.list_recent()
    assert listed["meetings"]


def test_empty_transcript():
    assert "error" in meetings.parse("")
