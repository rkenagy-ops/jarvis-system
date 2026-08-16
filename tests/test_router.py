from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import graph, router


def test_router_social():
    assert "social" in router.suggest("draft instagram captions for next week")
    assert "trader" in router.suggest("analyze NVDA rsi")


def test_graph_pack(tmp_path, monkeypatch):
    from app import obsidian

    monkeypatch.setattr(obsidian.config, "VAULT_DIR", tmp_path / "v")
    monkeypatch.setattr(graph.obsidian, "vault", obsidian.vault)
    obsidian.init_vault()
    pack = graph.pack("Home")
    assert "KNOWLEDGE GRAPH" in pack
    assert graph.build()["nodes"] >= 1
