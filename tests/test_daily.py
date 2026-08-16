from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import daily, memory, obsidian


def test_seed_and_pack(tmp_path, monkeypatch):
    monkeypatch.setattr(obsidian.config, "VAULT_DIR", tmp_path / "v")
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "t.db")
    memory.init()
    out = daily.seed_owner()
    assert "People/Rhett Kenagy.md" in out["notes"]
    assert (tmp_path / "v" / "Skills" / "why-not-docker.md").is_file()
    again = daily.seed_owner()
    assert "People/Rhett Kenagy.md" not in again["notes"]
    pack = daily.pack()
    assert pack["vault"]
    assert "greeting" in pack


def test_open_vault_reports_path(tmp_path, monkeypatch):
    monkeypatch.setattr(obsidian.config, "VAULT_DIR", tmp_path / "v")
    obsidian.init_vault()
    monkeypatch.setattr(daily, "obsidian_exe", lambda: None)
    monkeypatch.setattr(daily.webbrowser, "open", lambda uri: True)
    monkeypatch.setattr(daily.subprocess, "Popen", lambda *a, **k: None)
    out = daily.open_vault()
    assert out["ok"]
    assert str(tmp_path / "v") in out["path"]
