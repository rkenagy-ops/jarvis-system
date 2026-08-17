from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import backup, eval as eval_mod, finish, xpost


def test_oauth_header_shape(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "X_API_KEY", "ck")
    monkeypatch.setattr(config, "X_API_SECRET", "cs")
    monkeypatch.setattr(config, "X_ACCESS_TOKEN", "at")
    monkeypatch.setattr(config, "X_ACCESS_SECRET", "ats")
    h = xpost.oauth1_header("POST", "https://api.x.com/2/tweets")
    assert h.startswith("OAuth ")
    assert "oauth_signature=" in h


def test_eval_writes(tmp_path, monkeypatch):
    from app import memory, obsidian

    monkeypatch.setattr(obsidian.config, "VAULT_DIR", tmp_path / "v")
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "t.db")
    memory.init()
    obsidian.init_vault()
    monkeypatch.setattr(eval_mod.intel, "desk", lambda: {"movers": [{"symbol": "NVDA", "change_pct": 2}], "news": [{"title": "x"}]})
    out = eval_mod.score("NVDA ripped. Briefing.")
    assert out["score"] == 1.0
    assert "NVDA" in out["hit"]


def test_backup_zip(tmp_path, monkeypatch):
    from app import config, obsidian

    monkeypatch.setattr(config, "VAULT_DIR", tmp_path / "v")
    monkeypatch.setattr(config, "WORKSPACE_DIR", tmp_path / "w")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "j.db")
    (tmp_path / "j.db").write_bytes(b"sqlite")
    monkeypatch.setattr(obsidian.config, "VAULT_DIR", tmp_path / "v")
    obsidian.init_vault()
    out = backup.run()
    assert out["ok"]
    assert Path(out["path"]).is_file()
    assert out["files"] >= 1


def test_finish_checklist():
    c = finish.checklist()
    assert c["total"] >= 8
    assert "items" in c
