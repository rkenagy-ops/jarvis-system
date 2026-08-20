from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.xai import spoken_excerpt


def test_spoken_excerpt_strips_and_dedupes():
    text = "## Morning briefing\n\nWeather is fine. Weather is fine. **Markets** ripped.\n```code``` extra dump"
    out = spoken_excerpt(text)
    assert "Weather is fine." in out
    assert out.lower().count("weather is fine") == 1
    assert "```" not in out
    assert len(out) <= 180
