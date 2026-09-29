"""Free conductor: route to open APIs and local tools when Grok has no credits."""

from __future__ import annotations

import json
import re
from typing import Any

from . import autonomy, catalog, github_oss, markets, obsidian, widgets

TICKER = re.compile(r"\b([A-Z]{1,5}(?:-USD)?)\b")


def _fmt(value: Any, limit: int = 1800) -> str:
    if isinstance(value, str):
        return value[:limit]
    try:
        text = json.dumps(value, indent=2, default=str, ensure_ascii=False)
    except TypeError:
        text = str(value)
    return text[:limit]


def _tickers(text: str) -> list[str]:
    skip = {
        "I", "A", "THE", "AND", "FOR", "BUY", "SELL", "USD", "CEO", "API", "OSS", "SEC", "NWS",
        "RSI", "SMA", "WHAT", "SHOW", "GIVE", "TELL", "SCAN", "OPEN", "LIVE", "FREE",
        "READ", "CHART", "ON", "ME", "IS", "ANY", "OF", "IN", "TO", "MY", "RADAR", "SETUP", "HOW", "DOES", "LOOK",
    }
    found = []
    for m in TICKER.findall(text.upper().replace("$", " ")):
        if m not in skip and m not in found:
            found.append(m)
    return found[:5]


def _trading(text: str, low: str, use, emit) -> dict[str, Any] | None:
    """The trading desk without Grok: hunter, candles, journal and setups by keyword.

    Free mode is a keyword router, so a module it has no route to is invisible here no
    matter how well it is wired into tools.py.
    """
    syms = _tickers(text)
    if re.search(r"\b(hunt|hunter|universe|top (longs|shorts|picks)|best (trades|setups)|scan the market)\b", low):
        from . import hunter

        use("hunter", action="last")
        out = hunter.last()
        if not out.get("ok"):
            return {"text": out.get("note") or "No hunt yet - bot-28 runs one every 15 minutes.", "calls": [], "brain": "free"}
        rows = [f"Hunt {out['at'][:16]}Z ({out['session']}) - {out['universe']['liquid']} liquid names, {out['signals']} signals."]
        for title, key in (("Longs", "longs"), ("Shorts", "shorts")):
            rows.append(f"\n**{title}**")
            rows.extend(
                f"- {r['symbol']} {r['setup']} score {r['score']}: entry {r['entry']} stop {r['stop']} "
                f"target {r['target']} ({r['r_multiple']}R), rvol {r['rvol']}"
                for r in out[key][:8]
            )
        if out.get("loading"):
            rows.append("\n**Loading**")
            rows.extend(f"- {r['symbol']} {r['direction']} trigger {r['trigger']} stop {r['stop']}" for r in out["loading"][:6])
        return {"text": "\n".join(rows), "calls": [{"name": "hunter", "arguments": {"action": "last"}}], "brain": "free"}

    if re.search(r"\b(journal|mistakes?|lessons?|what (have you|did you) learn)", low):
        from . import journal

        use("journal", action="insights")
        view = journal.insights()
        o = view["overall"]
        rows = [f"Closed signals: {view['closed']}."]
        if o.get("trades"):
            rows.append(f"Overall {o['expectancy_r']:+}R/trade, win rate {o['win_rate']}%, total {o['total_r']:+}R.")
        rows += [f"Paying: {', '.join(view['best']) or 'nothing yet'}", f"Bleeding: {', '.join(view['worst']) or 'nothing yet'}"]
        rows += view["rules"] + view["edges"]
        rows += [f"- {m}: {cost}R" for m, cost in view["mistake_cost_r"].items()]
        return {"text": "\n".join(rows), "calls": [{"name": "journal", "arguments": {"action": "insights"}}], "brain": "free"}

    if syms and re.search(r"\b(candles?|chart|breakout|breakdown|radar|setups?|pattern)", low):
        from . import candles, setups

        chunks = []
        for s in syms[:3]:
            use("candles", action="radar", symbol=s)
            radar = candles.radar(s)
            read = candles.read(s)
            scan = setups.scan(s)
            if radar.get("error"):
                chunks.append(f"**{s}**: {radar['error']}")
                continue
            pats = ", ".join(f"{p['pattern']} ({p['strength']})" for p in read.get("patterns") or []) or "none"
            found = ", ".join(f"{f['setup']} [{f['confidence']}]" for f in scan.get("found") or []) or "none"
            chunks.append(
                f"**{s}** {radar['status']} ({radar['direction']}), close {radar['close']}, rvol {radar['rvol']}. "
                f"Long trigger {radar['long_trigger']} / short trigger {radar['short_trigger']}.\n"
                f"Candles: {pats}. Lean: {read.get('lean')}.\nSetups: {found}."
            )
        if emit:
            emit({"type": "tool_result", "name": "candles", "result": chunks})
        return {"text": "\n\n".join(chunks), "calls": [{"name": "candles", "arguments": {"symbols": syms[:3]}}], "brain": "free"}
    return None


def handle(user_text: str, emit=None) -> dict[str, Any]:
    text = (user_text or "").strip()
    low = text.lower()
    calls: list[dict] = []

    def use(name: str, **args) -> Any:
        calls.append({"name": name, "arguments": args})
        if emit:
            emit({"type": "tool_call", "name": name, "arguments": args})
        return args

    if emit:
        emit({"type": "status", "text": "free brain — open APIs online"})
        emit({"type": "agent_start", "agent": "jarvis"})

    if re.search(r"\b(hi|hello|hey|good (morning|afternoon|evening)|who are you)\b", low):
        from . import skills as skills_mod

        out = (
            f"{skills_mod.greeting()} **Free mode** — Grok takes over when the xAI team has credits. "
            "I can still brief you, quote markets, search the vault, pull GitHub OSS, weather, news, wiki, SEC, arXiv, and the rest of the catalog."
        )
        return {"text": out, "calls": calls, "brain": "free"}

    if "what do you think" in low or (low.startswith("jarvis") and "think" in low):
        from . import room

        return {"text": room.context(), "calls": [{"name": "room", "arguments": {}}], "brain": "free"}

    if "start my day" in low or "daily pack" in low or "daily driver" in low:
        from . import daily as daily_mod

        return {"text": _fmt(daily_mod.pack()), "calls": [{"name": "desktop", "arguments": {"action": "daily"}}], "brain": "free"}
    if "open vault" in low or "open obsidian" in low:
        from . import daily as daily_mod

        return {"text": _fmt(daily_mod.open_vault()), "calls": [{"name": "desktop", "arguments": {"action": "vault"}}], "brain": "free"}

    if "plan my day" in low or "plan the day" in low:
        from . import desktop

        plan = desktop.plan_day()
        return {"text": _fmt(plan), "calls": [{"name": "desktop", "arguments": {"action": "plan_day"}}], "brain": "free"}

    if "brief" in low or ("morning" in low and "good" not in low):
        use("briefing")
        result = autonomy.briefing()
        if emit:
            emit({"type": "tool_result", "name": "briefing", "result": result})
        return {"text": result + "\n\n(Free mode — written to today's daily note.)", "calls": calls, "brain": "free"}

    if re.search(r"\bjoke\b", low) or "make me laugh" in low:
        from . import desktop

        return {"text": desktop.joke()["joke"], "calls": [{"name": "desktop", "arguments": {"action": "joke"}}], "brain": "free"}

    if "screenshot" in low or "capture the screen" in low:
        from . import desktop

        return {"text": _fmt(desktop.screenshot()), "calls": [{"name": "desktop", "arguments": {"action": "screenshot"}}], "brain": "free"}

    if low.startswith("google ") or "search google" in low:
        from . import desktop

        q = re.sub(r".*(google|search google)\s+", "", low, count=1).strip() or text
        return {"text": str(desktop.google(q)), "calls": [{"name": "desktop", "arguments": {"action": "google"}}], "brain": "free"}

    if re.search(r"\b(timer|set a timer)\b", low):
        from . import desktop

        mins = 5
        m = re.search(r"\b(\d+)\s*(min|minute|minutes|sec|second|seconds)\b", low)
        if m:
            mins = int(m.group(1))
            if m.group(2).startswith("sec"):
                mins = max(1, (mins + 59) // 60)
        return {"text": _fmt(desktop.timer(mins)), "calls": [{"name": "desktop", "arguments": {"action": "timer"}}], "brain": "free"}

    if low.startswith("define ") or re.search(r"what does .+ mean", low):
        q = re.sub(r"^(define|what does)\s+", "", low)
        q = re.sub(r"\s+mean\??$", "", q).strip() or text
        use("catalog", source="dictionary", query=q)
        return {"text": _fmt(catalog.call("dictionary", q)), "calls": calls, "brain": "free"}

    if "translate" in low:
        q = re.sub(r"^translate\s+", "", text, flags=re.I).strip() or text
        use("catalog", source="translate", query=q)
        return {"text": _fmt(catalog.call("translate", q)), "calls": calls, "brain": "free"}

    if low.startswith("find ") or "find file" in low:
        from . import desktop

        q = re.sub(r".*(find file|find)\s+", "", text, count=1, flags=re.I).strip() or text
        return {"text": _fmt(desktop.find(q)), "calls": [{"name": "desktop", "arguments": {"action": "find"}}], "brain": "free"}

    if re.search(r"\bremind me\b", low) or low.startswith("remind "):
        from . import desktop

        title = re.sub(r".*remind(?: me)?(?: to)?\s+", "", text, count=1, flags=re.I).strip() or text
        mins = 0
        m = re.search(r"\bin (\d+)\s*(min|minute|minutes)\b", low)
        if m:
            mins = int(m.group(1))
        return {"text": _fmt(desktop.remind(title, minutes=mins)), "calls": [{"name": "desktop", "arguments": {"action": "remind"}}], "brain": "free"}

    if "take a note" in low or "save a note" in low:
        from . import desktop

        body = re.sub(r".*(take a note|save a note)[:\s]*", "", text, count=1, flags=re.I).strip() or text
        return {"text": _fmt(desktop.note(body)), "calls": [{"name": "desktop", "arguments": {"action": "note"}}], "brain": "free"}

    if low.startswith("open ") and not low.startswith("open source"):
        from . import desktop

        target = text[5:].strip()
        if target.startswith("http"):
            result = desktop.open_url(target)
        else:
            result = desktop.open_app(target.split()[0] if target else "")
            if result.get("error") and target:
                result = desktop.google(target)
        return {"text": _fmt(result), "calls": [{"name": "desktop", "arguments": {"action": "open"}}], "brain": "free"}

    if "youtube" in low or "play " in low:
        q = re.sub(r".*(youtube|play)\s+", "", low, count=1).strip() or text
        from . import desktop

        return {"text": str(desktop.youtube(q)), "calls": [{"name": "desktop", "arguments": {"action": "youtube"}}], "brain": "free"}
    if "map" in low or "where is" in low or "navigate" in low:
        from . import desktop

        q = re.sub(r".*(map|where is|navigate to)\s+", "", low, count=1).strip() or text
        return {"text": str(desktop.maps(q))[:800], "calls": [{"name": "desktop", "arguments": {"action": "maps"}}], "brain": "free"}
    if "weather" in low:
        use("weather")
        w = widgets.weather()
        if emit:
            emit({"type": "tool_result", "name": "weather", "result": w})
        cur = w.get("current") or {}
        return {"text": f"Weather ({w.get('place')}): {cur.get('temperature_2m')} C, wind {cur.get('wind_speed_10m')}, humidity {cur.get('relative_humidity_2m')}%.", "calls": calls, "brain": "free"}

    if "live feed" in low or "yahoo finance" in low or ("feeds" in low and "open" not in low):
        from . import feeds as feeds_mod

        snap = feeds_mod.snapshot()
        lines = [f"- {q.get('symbol')} {q.get('price')} ({q.get('change_pct')})" for q in snap.get("quotes") or [] if q.get("price") is not None]
        lines.append("")
        lines.extend([f"- [{n.get('source')}] {n.get('title')}" for n in (snap.get("news") or [])[:8]])
        return {"text": "Live feeds\n" + "\n".join(lines), "calls": [{"name": "feeds", "arguments": {}}], "brain": "free"}

    trading = _trading(text, low, use, emit)
    if trading:
        return trading

    if "news" in low or "headlines" in low:
        use("news")
        n = widgets.news()
        if emit:
            emit({"type": "tool_result", "name": "news", "result": n})
        lines = [f"- {i.get('title')}" for i in (n.get("items") or [])[:6]]
        return {"text": "Headlines:\n" + "\n".join(lines), "calls": calls, "brain": "free"}

    if "intel" in low or "news+market" in low or "all market" in low or "market desk" in low:
        from . import intel

        return {"text": _fmt(intel.desk()), "calls": [{"name": "market", "arguments": {"action": "intel"}}], "brain": "free"}

    if any(w in low for w in ("watchlist", "scan market", "markets", "how is the market")):
        use("market", action="watchlist")
        rows = markets.watchlist()
        if emit:
            emit({"type": "tool_result", "name": "market", "result": rows})
        lines = []
        for q in rows:
            if q.get("error"):
                continue
            pct = q.get("change_pct")
            tail = f" ({pct:+.2f}%)" if isinstance(pct, (int, float)) else ""
            lines.append(f"- {q.get('symbol')} {q.get('price')}{tail}")
        return {"text": "Watchlist:\n" + "\n".join(lines), "calls": calls, "brain": "free"}

    if "analyze" in low or "quote" in low or "price of" in low or "how is" in low:
        syms = _tickers(text)
        if syms:
            chunks = []
            for s in syms:
                use("market", action="analyze", symbol=s)
                data = markets.analyze(s)
                if emit:
                    emit({"type": "tool_result", "name": "market", "result": data})
                st = data.get("stats") or {}
                q = data.get("quote") or {}
                chunks.append(
                    f"**{s}** last {q.get('price')} ({q.get('change_pct')}%). "
                    f"RSI {st.get('rsi14')}, trend {st.get('trend')}, SMA20 {st.get('sma20')}."
                )
            return {"text": "\n".join(chunks), "calls": calls, "brain": "free"}

    if re.search(r"\b(buy|sell)\b", low) and _tickers(text):
        side = "buy" if "buy" in low else "sell"
        qty_m = re.search(r"\b(\d+(?:\.\d+)?)\b", low)
        qty = float(qty_m.group(1)) if qty_m else 1
        sym = _tickers(text)[0]
        use("market", action="trade", symbol=sym, side=side, qty=qty)
        fill = markets.paper_trade(sym, side, qty)
        if emit:
            emit({"type": "tool_result", "name": "market", "result": fill})
        return {"text": f"Paper {side}: {_fmt(fill)}", "calls": calls, "brain": "free"}

    if "task" in low:
        use("obsidian", action="tasks")
        tasks = obsidian.list_tasks(open_only=True)
        if emit:
            emit({"type": "tool_result", "name": "obsidian", "result": tasks})
        if not tasks:
            return {"text": "No open vault tasks.", "calls": calls, "brain": "free"}
        lines = [f"- {t['text']} ({t['path']}:{t['line']})" for t in tasks[:12]]
        return {"text": "Open tasks:\n" + "\n".join(lines), "calls": calls, "brain": "free"}

    if "vault" in low or "obsidian" in low or "remember" in low and "search" in low:
        q = re.sub(r"\b(search|the|vault|obsidian|for|notes?)\b", " ", low)
        q = " ".join(q.split()) or text
        use("obsidian", action="search", query=q)
        hits = obsidian.search(q)
        if emit:
            emit({"type": "tool_result", "name": "obsidian", "result": hits})
        rows = hits.get("results") or []
        if not rows:
            return {"text": f"No vault hits for {q!r}.", "calls": calls, "brain": "free"}
        lines = [f"- {h['path']}: {h.get('snippet','')[:160]}" for h in rows[:8]]
        return {"text": "Vault:\n" + "\n".join(lines), "calls": calls, "brain": "free"}

    if "github" in low or low.startswith("oss") or "open source" in low or "ingest" in low:
        q = text
        for prefix in ("search github", "github", "oss search", "ingest"):
            if prefix in low:
                q = text[low.find(prefix) + len(prefix) :].strip() or q
        if "ingest" in low and "/" in text:
            repo = next((p for p in text.split() if "/" in p), "")
            use("oss", action="ingest", repo=repo)
            result = github_oss.ingest(repo)
            if emit:
                emit({"type": "tool_result", "name": "oss", "result": result})
            return {"text": f"Ingested {repo} → {result.get('vault')}", "calls": calls, "brain": "free"}
        use("oss", action="search", query=q)
        result = github_oss.search(q or "jarvis assistant", 6)
        if emit:
            emit({"type": "tool_result", "name": "oss", "result": result})
        lines = [f"- {r.get('full_name')} ({r.get('stars')}★) {r.get('description')}" for r in result.get("repos") or []]
        return {"text": "GitHub OSS:\n" + "\n".join(lines), "calls": calls, "brain": "free"}

    catalog_hit = None
    for src in catalog.SOURCES:
        if re.search(rf"\b{re.escape(src)}\b", low.replace("-", "_")) or src.replace("_", " ") in low:
            catalog_hit = src
            break
    if catalog_hit or any(w in low for w in ("arxiv", "sec", "cve", "wiki", "define", "geocode", "pypi")):
        src = catalog_hit or (
            "arxiv" if "arxiv" in low else
            "sec_edgar" if "sec" in low else
            "cve" if "cve" in low else
            "dictionary" if "define" in low else
            "geocode" if "geocode" in low or "where is" in low else
            "pypi" if "pypi" in low else
            "duckduckgo"
        )
        q = text
        use("catalog", source=src, query=q)
        result = catalog.call(src, q)
        if emit:
            emit({"type": "tool_result", "name": "catalog", "result": result})
        return {"text": f"{src}:\n{_fmt(result)}", "calls": calls, "brain": "free"}

    if any(ch in text for ch in "+*/") and re.search(r"\d", text):
        expr = text.replace("what is", "").replace("calculate", "").strip()
        use("calc", expression=expr)
        result = widgets.calc(expr)
        return {"text": _fmt(result), "calls": calls, "brain": "free"}

    if any(w in low for w in ("time", "date", "utc")):
        return {"text": _fmt(widgets.now()), "calls": calls, "brain": "free"}

    if low in {"help", "?", "what can you do", "capabilities", "tools"} or re.search(
        r"what can you do|what tools|list (your |all )?tools|show (me )?(your |all )?tools", low
    ):
        from . import skills as skills_mod

        return {"text": skills_mod.help_text() + "\n\nGrok returns automatically after credits are on the xAI team.", "calls": calls, "brain": "free"}

    use("catalog", source="duckduckgo", query=text)
    ddg = catalog.call("duckduckgo", text)
    use("wiki", query=text)
    try:
        wiki = widgets.wiki(text)
    except Exception as exc:
        wiki = {"error": str(exc)}
    vault = obsidian.search(text)
    if emit:
        emit({"type": "tool_result", "name": "catalog", "result": ddg})
        emit({"type": "tool_result", "name": "wiki", "result": wiki})
    bits = []
    if ddg.get("abstract"):
        bits.append(ddg["abstract"])
    elif ddg.get("related"):
        bits.append("Related: " + "; ".join(ddg["related"][:4]))
    if wiki.get("extract"):
        bits.append(wiki["extract"][:500])
        if wiki.get("url"):
            bits.append(wiki["url"])
    hits = vault.get("results") or []
    if hits:
        bits.append("Vault: " + ", ".join(h["path"] for h in hits[:4]))
    if not bits:
        bits.append("Free mode had no instant answer. Try: briefing, quote AAPL, weather, or catalog arxiv <topic>.")
    bits.append("\n_Grok will take this over once xAI credits are live._")
    return {"text": "\n\n".join(bits), "calls": calls, "brain": "free"}
