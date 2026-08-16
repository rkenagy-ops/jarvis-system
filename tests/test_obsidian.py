from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import obsidian, opensource


def test_vault_write_search_and_jail(tmp_path, monkeypatch):
    monkeypatch.setattr(obsidian.config, "VAULT_DIR", tmp_path / "vault")
    obsidian.init_vault()
    home = obsidian.read_note("00 Home.md")
    assert "Jarvis" in home["text"]
    obsidian.write_note("Projects/alpha.md", "# Alpha\n\nSee [[00 Home]]\n")
    hits = obsidian.search("Alpha")
    assert hits["results"]
    links = obsidian.backlinks("00 Home")
    assert any("alpha" in p.lower() for p in links["backlinks"])
    try:
        obsidian.resolve("../../secret.md")
        assert False, "should jail"
    except ValueError:
        pass


def test_crawl_rejects_file():
    assert "error" in opensource.crawl("file:///etc/passwd")


def test_calendar(tmp_path, monkeypatch):
    monkeypatch.setattr(obsidian.config, "VAULT_DIR", tmp_path / "vault")
    opensource.calendar_add("Review trades", "2026-08-20T09:00", "paper only")
    listed = opensource.calendar_list()
    assert listed["events"]
    assert listed["events"][0]["title"] == "Review trades"
