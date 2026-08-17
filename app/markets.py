from __future__ import annotations

import math
import sqlite3
import time
import uuid
from typing import Any

import httpx

from . import config, memory

UA = {"User-Agent": "Mozilla/5.0 SuperJarvis/1.2", "Accept": "application/json"}
CRYPTO = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
}


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    conn = _db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS paper_account (
            id INTEGER PRIMARY KEY CHECK (id=1),
            cash REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS paper_positions (
            symbol TEXT PRIMARY KEY,
            qty REAL NOT NULL,
            avg_price REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS paper_trades (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            qty REAL NOT NULL,
            price REAL NOT NULL,
            mode TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        """
    )
    if not conn.execute("SELECT 1 FROM paper_account WHERE id=1").fetchone():
        conn.execute(
            "INSERT INTO paper_account(id, cash, updated_at) VALUES(1,?,?)",
            (config.PAPER_CASH, time.time()),
        )
    conn.commit()
    conn.close()


def _yahoo_chart(symbol: str, range_: str = "6mo", interval: str = "1d") -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    with httpx.Client(timeout=20.0, headers=UA) as client:
        resp = client.get(url, params={"range": range_, "interval": interval})
        resp.raise_for_status()
        return resp.json()


def quote(symbol: str) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    try:
        data = _yahoo_chart(symbol, range_="5d", interval="1d")
        result = ((data.get("chart") or {}).get("result") or [None])[0]
        if not result:
            raise ValueError("no chart")
        meta = result.get("meta") or {}
        closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        last = meta.get("regularMarketPrice") or next((c for c in reversed(closes) if c is not None), None)
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        change = None
        pct = None
        if last is not None and prev:
            change = last - prev
            pct = (change / prev) * 100
        return {
            "symbol": symbol,
            "price": last,
            "previous": prev,
            "change": change,
            "change_pct": pct,
            "currency": meta.get("currency"),
            "exchange": meta.get("exchangeName"),
            "source": "yahoo",
        }
    except Exception as exc:
        if symbol in CRYPTO or symbol.replace("-USD", "") in CRYPTO:
            cg = CRYPTO.get(symbol) or CRYPTO.get(symbol.replace("-USD", ""))
            with httpx.Client(timeout=15.0, headers=UA) as client:
                r = client.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": cg, "vs_currencies": "usd", "include_24hr_change": "true"},
                )
                r.raise_for_status()
                row = r.json().get(cg) or {}
            return {
                "symbol": symbol,
                "price": row.get("usd"),
                "change_pct": row.get("usd_24h_change"),
                "currency": "USD",
                "source": "coingecko",
            }
        return {"symbol": symbol, "error": str(exc)}


def history(symbol: str, range_: str = "6mo") -> dict[str, Any]:
    symbol = symbol.strip().upper()
    data = _yahoo_chart(symbol, range_=range_, interval="1d")
    result = ((data.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return {"error": f"No history for {symbol}"}
    ts = result.get("timestamp") or []
    q = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    rows = []
    for i, t in enumerate(ts):
        close = (q.get("close") or [None])[i] if i < len(q.get("close") or []) else None
        if close is None:
            continue
        rows.append(
            {
                "t": t,
                "open": (q.get("open") or [None])[i] if i < len(q.get("open") or []) else None,
                "high": (q.get("high") or [None])[i] if i < len(q.get("high") or []) else None,
                "low": (q.get("low") or [None])[i] if i < len(q.get("low") or []) else None,
                "close": close,
                "volume": (q.get("volume") or [None])[i] if i < len(q.get("volume") or []) else None,
            }
        )
    return {"symbol": symbol, "bars": rows[-400:], "count": len(rows)}


def _series(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
        else:
            chunk = values[i + 1 - window : i + 1]
            out.append(sum(chunk) / window)
    return out


def indicators(closes: list[float]) -> dict[str, Any]:
    if len(closes) < 15:
        return {"error": "Need at least 15 closes"}
    sma20 = _series(closes, min(20, len(closes)))[-1]
    sma50 = _series(closes, min(50, len(closes)))[-1] if len(closes) >= 50 else None
    rets = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes)) if closes[i - 1]]
    vol = (sum(r * r for r in rets[-20:]) / max(1, min(20, len(rets)))) ** 0.5 if rets else 0
    # RSI 14
    gains, losses = [], []
    for r in rets[-14:]:
        gains.append(max(r, 0))
        losses.append(max(-r, 0))
    avg_g = sum(gains) / len(gains) if gains else 0
    avg_l = sum(losses) / len(losses) if losses else 0
    rsi = 100 - (100 / (1 + (avg_g / avg_l))) if avg_l else 100
    # MACD 12/26
    ema = closes[0]
    e12 = e26 = ema
    k12, k26 = 2 / 13, 2 / 27
    macd_line = []
    for c in closes:
        e12 = c * k12 + e12 * (1 - k12)
        e26 = c * k26 + e26 * (1 - k26)
        macd_line.append(e12 - e26)
    signal = macd_line[0]
    k9 = 2 / 10
    for m in macd_line:
        signal = m * k9 + signal * (1 - k9)
    last = closes[-1]
    prev = closes[-2]
    return {
        "last": last,
        "change_1d_pct": (last / prev - 1) * 100 if prev else None,
        "sma20": sma20,
        "sma50": sma50,
        "rsi14": rsi,
        "macd": macd_line[-1],
        "macd_signal": signal,
        "realized_vol_20d": vol * math.sqrt(252) if vol else 0,
        "high_20": max(closes[-20:]),
        "low_20": min(closes[-20:]),
        "trend": "up" if sma20 and last > sma20 else "down",
    }


def analyze(symbol: str, range_: str = "6mo") -> dict[str, Any]:
    hist = history(symbol, range_)
    if hist.get("error"):
        return hist
    closes = [b["close"] for b in hist["bars"] if b.get("close") is not None]
    stats = indicators(closes)
    q = quote(symbol)
    return {"symbol": symbol.upper(), "quote": q, "stats": stats, "bars": len(closes)}


def watchlist(symbols: list[str] | None = None) -> list[dict]:
    out = []
    for s in symbols or config.WATCHLIST:
        out.append(quote(s))
    return out


def account() -> dict[str, Any]:
    init()
    conn = _db()
    cash = conn.execute("SELECT cash FROM paper_account WHERE id=1").fetchone()[0]
    positions = [dict(r) for r in conn.execute("SELECT * FROM paper_positions WHERE qty != 0").fetchall()]
    trades = [dict(r) for r in conn.execute("SELECT * FROM paper_trades ORDER BY created_at DESC LIMIT 20").fetchall()]
    conn.close()
    marked = []
    equity = cash
    for p in positions:
        q = quote(p["symbol"])
        px = q.get("price") or p["avg_price"]
        value = px * p["qty"]
        pnl = (px - p["avg_price"]) * p["qty"]
        equity += value
        marked.append({**p, "last": px, "value": value, "unrealized_pnl": pnl})
    return {
        "mode": config.TRADING_MODE,
        "cash": cash,
        "equity": equity,
        "positions": marked,
        "trades": trades,
        "confirm_required": config.TRADING_REQUIRE_CONFIRMATION,
    }


def paper_trade(symbol: str, side: str, qty: float, *, confirm_token: str | None = None) -> dict[str, Any]:
    init()
    symbol = symbol.strip().upper()
    side = side.lower()
    qty = float(qty)
    if side not in {"buy", "sell"} or qty <= 0:
        return {"error": "side must be buy/sell and qty > 0"}
    q = quote(symbol)
    price = q.get("price")
    if not price:
        return {"error": f"No price for {symbol}", "quote": q}

    if config.TRADING_MODE == "live":
        if not confirm_token:
            pending = memory.create_pending(
                "live_trade",
                {"symbol": symbol, "side": side, "qty": qty, "price": price},
                ttl_sec=180,
            )
            return {
                "blocked": True,
                "reason": "Live mode requires confirm_token. Call confirm_trade with this token.",
                **pending,
            }
        consumed = memory.consume_pending(confirm_token)
        if not consumed or consumed.get("kind") != "live_trade":
            return {"error": "Invalid or expired confirm token. Live trade cancelled."}
        from . import broker

        if broker.configured():
            routed = broker.submit_market(symbol, side, qty)
            memory.remember(
                f"alpaca {side} {qty} {symbol} → {routed}",
                kind="trade",
                tags=["trade", "alpaca", symbol],
                importance=0.85,
                source_agent="trader",
            )
            return routed
        return {
            "error": "Live mode is on but ALPACA_KEY_ID / ALPACA_SECRET_KEY are not set. No fill.",
            "hint": "Create keys at https://app.alpaca.markets . ALPACA_LIVE=true is real cash.",
        }

    if config.TRADING_REQUIRE_CONFIRMATION and qty * price >= 25000 and not confirm_token:
        pending = memory.create_pending(
            "large_paper",
            {"symbol": symbol, "side": side, "qty": qty, "price": price},
            ttl_sec=180,
        )
        return {"blocked": True, "reason": "Large paper order needs confirm_token.", **pending}

    return _fill(symbol, side, qty, price, mode="paper")


def confirm_trade(token: str) -> dict[str, Any]:
    item = memory.consume_pending(token)
    if not item:
        return {"error": "Invalid or expired confirm token."}
    payload = item["payload"]
    if item.get("kind") == "live_trade":
        from . import broker

        if broker.configured():
            return broker.submit_market(payload["symbol"], payload["side"], float(payload["qty"]))
        return {"error": "Confirm received but Alpaca keys are missing. No live fill."}
    return _fill(payload["symbol"], payload["side"], float(payload["qty"]), float(payload["price"]), mode="paper-confirmed")


def _fill(symbol: str, side: str, qty: float, price: float, mode: str) -> dict[str, Any]:
    conn = _db()
    cash = conn.execute("SELECT cash FROM paper_account WHERE id=1").fetchone()[0]
    pos = conn.execute("SELECT qty, avg_price FROM paper_positions WHERE symbol=?", (symbol,)).fetchone()
    held = pos["qty"] if pos else 0.0
    avg = pos["avg_price"] if pos else 0.0
    if side == "buy":
        cost = qty * price
        if cost > cash + 1e-6:
            conn.close()
            return {"error": f"Insufficient paper cash ({cash:.2f}) for {cost:.2f}"}
        new_qty = held + qty
        new_avg = ((held * avg) + cost) / new_qty if new_qty else 0
        cash -= cost
        conn.execute(
            "INSERT INTO paper_positions(symbol, qty, avg_price) VALUES(?,?,?) ON CONFLICT(symbol) DO UPDATE SET qty=?, avg_price=?",
            (symbol, new_qty, new_avg, new_qty, new_avg),
        )
    else:
        if qty > held + 1e-9:
            conn.close()
            return {"error": f"Only {held} shares of {symbol} held"}
        cash += qty * price
        new_qty = held - qty
        if new_qty <= 1e-9:
            conn.execute("DELETE FROM paper_positions WHERE symbol=?", (symbol,))
        else:
            conn.execute("UPDATE paper_positions SET qty=? WHERE symbol=?", (new_qty, symbol))
    trade_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO paper_trades(id, symbol, side, qty, price, mode, created_at) VALUES(?,?,?,?,?,?,?)",
        (trade_id, symbol, side, qty, price, mode, time.time()),
    )
    conn.execute("UPDATE paper_account SET cash=?, updated_at=? WHERE id=1", (cash, time.time()))
    conn.commit()
    conn.close()
    memory.remember(
        f"{mode} {side} {qty} {symbol} @ {price:.4f}",
        kind="trade",
        tags=["trade", symbol, side],
        importance=0.7,
        source_agent="trader",
    )
    return {"ok": True, "id": trade_id, "symbol": symbol, "side": side, "qty": qty, "price": price, "cash": cash, "mode": mode}


def dispatch(action: str, **kwargs) -> Any:
    init()
    if action == "quote":
        return quote(kwargs.get("symbol") or "")
    if action == "history":
        return history(kwargs.get("symbol") or "", kwargs.get("range") or "6mo")
    if action == "analyze":
        return analyze(kwargs.get("symbol") or "", kwargs.get("range") or "6mo")
    if action == "watchlist":
        symbols = kwargs.get("symbols")
        if isinstance(symbols, str):
            symbols = [s.strip() for s in symbols.split(",") if s.strip()]
        return watchlist(symbols)
    if action == "account":
        return account()
    if action == "trade":
        return paper_trade(
            kwargs.get("symbol") or "",
            kwargs.get("side") or "buy",
            float(kwargs.get("qty") or 0),
            confirm_token=kwargs.get("confirm_token"),
        )
    if action == "confirm":
        return confirm_trade(kwargs.get("confirm_token") or kwargs.get("token") or "")
    if action == "scan":
        from . import intel

        return intel.scan(kwargs.get("universe") or kwargs.get("symbols") or "all")
    if action == "intel":
        from . import intel

        return intel.desk()
    if action == "broker":
        from . import broker

        return broker.account() if broker.configured() else broker.status()
    return {"error": f"Unknown market action {action}"}
