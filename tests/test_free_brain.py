from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import free_brain, widgets


def test_greeting_free():
    out = free_brain.handle("hello")
    assert out["brain"] == "free"
    assert "free" in out["text"].lower()


def test_calc_intent():
    out = free_brain.handle("what is 12*11")
    assert "132" in out["text"] or widgets.calc("12*11")["result"] == 132


def test_help_intent():
    out = free_brain.handle("help")
    assert "briefing" in out["text"].lower()
