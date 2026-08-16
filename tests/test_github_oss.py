from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import github_oss, tools


def test_split_repo():
    assert github_oss._split("https://github.com/public-apis/public-apis") == ("public-apis", "public-apis")
    assert github_oss._split("n8n-io/n8n") == ("n8n-io", "n8n")


def test_oss_tool_on_jarvis():
    names = {t.get("name") or t.get("type") for t in tools.tools_for("jarvis", allow_spawn=True)}
    assert "oss" in names


def test_oss_unknown_action():
    out = github_oss.dispatch("nope")
    assert "error" in out
    assert "jarvis_pack" in out["actions"]


def test_jarvis_pack_covers_the_field():
    assert "isair/jarvis" in github_oss.JARVIS_PACK
    assert "swapagarwal/JARVIS-on-Messenger" in github_oss.JARVIS_PACK
    assert "Melissa-AI/Melissa-Core" in github_oss.JARVIS_PACK
    assert len(github_oss.JARVIS_PACK) >= 16
