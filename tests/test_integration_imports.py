"""End-to-end import + wiring smoke test.

Unit tests import modules individually, which hides circular imports and a tool
that is registered in the schema but has no executor branch (or vice versa).
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_every_app_module_imports():
    import importlib

    failures = []
    for path in sorted((ROOT / "app").glob("*.py")):
        if path.stem.startswith("__"):
            continue
        try:
            importlib.import_module(f"app.{path.stem}")
        except Exception as exc:  # noqa: BLE001 - reporting all of them at once is the point
            failures.append(f"{path.stem}: {type(exc).__name__}: {exc}")
    assert not failures, "modules failed to import:\n" + "\n".join(failures)


def test_new_modules_expose_dispatch():
    from app import engage, oss, setups

    for mod in (engage, oss, setups):
        assert callable(mod.dispatch), f"{mod.__name__} has no dispatch"
        # an unknown action must be reported, never raise
        out = mod.dispatch("definitely-not-an-action")
        assert isinstance(out, dict) and "error" in out


def test_registered_tools_all_have_an_executor():
    """A tool in the schema with no executor branch silently returns the fallback."""
    from app import tools

    names = {t.get("name") or (t.get("function") or {}).get("name") for t in tools.tools_for("jarvis", allow_spawn=True)}
    names.discard(None)
    assert {"stack", "engage", "oss", "setups", "market"} <= names

    source = (ROOT / "app" / "tools.py").read_text(encoding="utf-8")
    for name in ("engage", "oss", "setups"):
        assert f'if name == "{name}":' in source, f"{name} is registered but has no executor branch"


def test_dispatch_tables_are_consistent():
    """Every network engage can auto-post to must have a replier, and vice versa."""
    from app import engage

    assert set(engage.REPLIERS) == set(engage.AUTO_NETWORKS)
    assert not (engage.AUTO_NETWORKS & engage.REVIEW_NETWORKS)
    assert engage.NETWORKS == engage.AUTO_NETWORKS | engage.REVIEW_NETWORKS
    # capabilities() must cover every network the runner can be pointed at
    caps = engage.capabilities()
    assert set(caps) == engage.NETWORKS


def test_setups_catalog_matches_planner():
    """Every catalogued setup must be plannable, and vice versa."""
    from app import setups

    planned = {"trend_pullback", "breakout_20d", "oversold_in_uptrend", "momentum_cross", "range_fade"}
    assert set(setups.CATALOG) == planned
