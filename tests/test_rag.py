from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import rag


def test_chunk_and_retrieve(tmp_path, monkeypatch):
    monkeypatch.setattr(rag.config, "DB_PATH", tmp_path / "rag.db")
    rag.init()
    rag.index_note(
        "Projects/alpha.md",
        "# Alpha\n\n## Thesis\nWe only paper-trade NVDA until RSI cools.\n\n## Risk\nNo live brokerage.\n",
    )
    hits = rag.retrieve("NVDA paper")
    assert hits
    assert any("NVDA" in h["text"] or "NVDA" in (h.get("heading") or "") for h in hits)
    pack = rag.pack("paper-trade")
    assert "VAULT RAG" in pack or "NVDA" in pack
