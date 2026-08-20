from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import memory, ops


def test_md_html():
    html = ops.md_to_html("# Hi\n\n**bold** and [x](https://x.com)")
    assert "<h1>" in html and "<strong>bold</strong>" in html and "href=" in html


def test_draft_and_confirm(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "ops.db")
    monkeypatch.setattr(ops.obsidian, "write_note", lambda *a, **k: {"ok": True, "path": "x.md"})
    memory.init()
    ops.init()
    item = ops.draft("Launch", "Hook\n\nCTA", kind="post", platforms=["x", "blog"])
    assert item["status"] == "draft"
    assert "<p>Hook</p>" in item["body_html"]
    pub = ops.publish(item["id"])
    assert pub.get("blocked")
    assert pub.get("confirm_token")
    ok = ops.publish(item["id"], confirm_token=pub["confirm_token"])
    assert ok.get("ok")
    blog = [r for r in ok["results"] if r.get("platform") == "blog"]
    assert blog


def test_youtube_publish_needs_confirm(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", tmp_path / "ops2.db")
    monkeypatch.setattr(ops.obsidian, "write_note", lambda *a, **k: {"ok": True, "path": "x.md"})
    memory.init()
    ops.init()
    item = ops.draft("Clip", "Watch this", kind="post", platforms=["youtube"])
    pub = ops.publish(item["id"])
    assert pub.get("blocked") is True
    assert pub.get("confirm_token")
