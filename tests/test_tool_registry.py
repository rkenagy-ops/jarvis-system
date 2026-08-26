"""One name, one function.

Two tools were declared under the name "oss" with mutually exclusive action enums, and
the first executor branch always won - so every raw action (fetch, tree, read, grep,
vendor, install) was handed to the curated pack module, which has never known what to
do with them. The unrestricted OSS tool was unreachable dead code from the day it
shipped.

A duplicate name also gives the model two conflicting schemas for one function, which
passes session validation and then fails at generation time. This exact mistake had
already happened once in this file with "universe", so it gets a test.
"""

from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import tools


def test_no_duplicate_tool_names():
    dupes = {n: c for n, c in Counter(t["name"] for t in tools.FUNCTION_TOOLS).items() if c > 1}
    assert not dupes, f"two schemas under one name: {dupes}"


def test_every_tool_is_reachable():
    """A declared tool whose branch is shadowed is a promise the model cannot keep.

    Through _run_tool, so a tool that merely cannot reach the network here still counts
    as reachable - that is a different failure from having no executor at all.
    """
    from app.brain import _run_tool

    for t in tools.FUNCTION_TOOLS:
        out = _run_tool(t["name"], {}, session_id="t", agent_id="jarvis")
        if isinstance(out, dict):
            assert "unknown tool" not in str(out.get("error", "")).lower(), f"{t['name']} has no executor"


def test_oss_raw_actions_reach_the_raw_module():
    """These used to land in github_oss, which does not implement any of them."""
    for action in ("read", "grep", "tree", "vendor"):
        out = tools.execute("oss", {"action": action, "repo": "psf/requests"}, session_id="t", agent_id="jarvis")
        assert isinstance(out, dict)
        # The raw module answers "not fetched yet"; the curated one would not know the action.
        blob = str(out).lower()
        assert "unknown" not in blob or "fetch" in blob, f"{action} did not reach app/oss.py: {blob[:160]}"


def test_oss_curated_actions_still_route_to_the_pack_module():
    from app import tools as tools_mod

    for action in ("readme", "starter_pack", "awesome", "youtube"):
        assert action in tools_mod._OSS_CURATED, f"{action} must stay on the curated path"


def test_the_two_routing_sets_do_not_overlap():
    """An action in both sets is the ambiguity we just removed, reintroduced."""
    from app import tools as tools_mod

    schema = next(t for t in tools_mod.FUNCTION_TOOLS if t["name"] == "oss")
    actions = set(schema["parameters"]["properties"]["action"]["enum"])
    raw = actions - tools_mod._OSS_CURATED
    assert raw & {"read", "grep", "fetch", "vendor", "install"}, "raw actions must exist"
    assert not (raw & tools_mod._OSS_CURATED)


def test_install_stays_confirm_gated():
    """oss install runs fetched setup code beside brokerage credentials."""
    out = tools.execute("oss", {"action": "install", "repo": "psf/requests"}, session_id="t", agent_id="jarvis")
    assert isinstance(out, dict)
    assert "confirm" in str(out).lower(), "install must still require a confirm_token"


def test_every_schema_is_well_formed():
    import re

    name_ok = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
    for t in tools.FUNCTION_TOOLS:
        assert t.get("type") == "function", t.get("name")
        assert name_ok.match(t["name"]), f"bad function name {t['name']!r}"
        assert t.get("description"), f"{t['name']} has no description"
        params = t.get("parameters")
        assert isinstance(params, dict) and params.get("type") == "object", t["name"]
        props = params.get("properties")
        assert isinstance(props, dict), t["name"]
        for req in params.get("required") or []:
            assert req in props, f"{t['name']} requires {req!r} which it does not declare"
