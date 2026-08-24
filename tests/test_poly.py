from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import poly


def test_kelly_positive_and_zero():
    hit = poly.kelly(0.6, 0.4, fraction=0.25, cap=0.10)
    assert hit["f"] > 0
    assert hit["edge"] > 0
    miss = poly.kelly(0.4, 0.55)
    assert miss["f"] == 0.0


def test_parse_market():
    row = {
        "id": "1",
        "question": "Will BTC hit 200k in 2026?",
        "slug": "btc-200k",
        "outcomePrices": '["0.22","0.78"]',
        "outcomes": '["Yes","No"]',
        "volume24hr": 120000,
        "liquidity": 50000,
        "closed": False,
    }
    parsed = poly._parse(row)
    assert parsed["yes"] == 0.22
    assert parsed["volume_24h"] == 120000
    assert "polymarket.com" in parsed["url"]


def test_bounce_uses_scan(monkeypatch, tmp_path):
    monkeypatch.setattr(poly.obsidian, "write_note", lambda *a, **k: {"ok": True, "path": "x.md"})
    monkeypatch.setattr(
        poly,
        "scan",
        lambda **k: {
            "ok": True,
            "markets": [
                {
                    "id": "1",
                    "question": "Extreme favorite",
                    "yes": 0.92,
                    "volume_24h": 9e6,
                    "url": "https://polymarket.com",
                    "slug": "x",
                }
            ],
        },
    )
    out = poly.bounce(limit=4, bankroll=1000)
    assert out["ok"] is True
    assert "ideas" in out
    assert out.get("disclaimer")


def test_dispatch_scan_mocked(monkeypatch):
    monkeypatch.setattr(poly, "scan", lambda **k: {"ok": True, "markets": [], "query": k.get("query")})
    out = poly.dispatch("scan", query="fed")
    assert out["ok"] is True


# --- instruction layer -------------------------------------------------------


def test_explain_lists_and_details():
    listing = poly.explain()
    assert listing["ok"]
    assert set(listing["order"]) == set(listing["primer"])
    one = poly.explain("kelly")
    assert one["ok"] and "quarter-Kelly" in one["explanation"]
    assert "error" in poly.explain("nonsense")


def test_evaluate_validates_inputs():
    assert "error" in poly.evaluate(price=0, p=0.5)
    assert "error" in poly.evaluate(price=1.5, p=0.5)
    assert "error" in poly.evaluate(price=0.5, p=0)
    assert "error" in poly.evaluate(price=0.5, p=1)
    assert "error" in poly.evaluate(price=0.5, p=0.6, bankroll=0)
    assert "error" in poly.evaluate(price="x", p=0.6)


def test_evaluate_thin_edge_is_no_go():
    out = poly.evaluate(price=0.60, p=0.61, bankroll=1000)
    assert out["verdict"] == "NO-GO"
    assert out["stake_usd"] == 0.0
    assert "error bar" in out["reasoning"]


def test_evaluate_real_edge_sizes_a_bet():
    out = poly.evaluate(price=0.50, p=0.70, bankroll=1000)
    assert out["verdict"] == "PAPER"
    assert out["side"] == "YES"
    assert out["stake_usd"] > 0
    assert out["shares"] > 0
    # never risks more than the cap
    assert out["stake_usd"] <= 1000 * 0.10


def test_evaluate_takes_no_side_when_overpriced():
    out = poly.evaluate(price=0.80, p=0.50, bankroll=1000)
    assert out["side"] == "NO"
    # entry price for NO is 1 - price
    assert abs(out["entry_price"] - 0.20) < 1e-9


def test_evaluate_max_loss_is_the_stake():
    out = poly.evaluate(price=0.40, p=0.65, bankroll=5000)
    if out["verdict"] == "PAPER":
        assert out["max_loss"] == out["stake_usd"]
        assert out["payoff_if_right"] > 0


def test_evaluate_dispatch_routes():
    assert poly.dispatch("explain")["ok"]
    out = poly.dispatch("evaluate", price=0.5, p=0.7, bankroll=1000)
    assert out["ok"] and out["verdict"] == "PAPER"
