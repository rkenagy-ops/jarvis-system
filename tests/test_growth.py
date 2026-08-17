from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import agents, growth, router, tools


def test_twenty_agents():
    assert len(agents.AGENTS) == 20
    assert agents.get("scout").id == "scout"
    assert agents.get("watcher").role == "Live feeds"


def test_router_growth():
    assert "scout" in router.suggest("ingest github open source plugins")
    assert "watcher" in router.suggest("breaking live feed headlines")


def test_growth_pack_list():
    assert "letta-ai/letta" in growth.GROWTH_PACK
    assert "langchain-ai/langgraph" in growth.GROWTH_PACK
    names = {t.get("name") or t.get("type") for t in tools.tools_for("jarvis", allow_spawn=True)}
    assert "oss" in names


def test_oss_actions_include_growth():
    from app import github_oss

    out = github_oss.dispatch("nope")
    assert "growth_pack" in out["actions"]
    assert "self_upgrade" in out["actions"]
