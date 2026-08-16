from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import catalog, tools


def test_catalog_registry():
    ids = {s["id"] for s in catalog.list_sources()}
    for name in ("arxiv", "jina", "sec_edgar", "geocode", "pypi", "cisa_kev", "fx", "dictionary"):
        assert name in ids
    assert len(ids) >= 30


def test_catalog_rejects_bad_url():
    assert "error" in catalog.call("jina", "file:///etc/passwd")
    assert "error" in catalog.call("not-a-source", "x")


def test_jarvis_has_catalog_tool():
    names = {t.get("name") or t.get("type") for t in tools.tools_for("jarvis", allow_spawn=True)}
    assert "catalog" in names
