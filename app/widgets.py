from __future__ import annotations

import ast
import math
import operator
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from xml.etree import ElementTree as ET

import httpx

UA = {"User-Agent": "SuperJarvis/1.2"}

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Mod: operator.mod,
}


def now() -> dict:
    utc = datetime.now(timezone.utc)
    return {"utc": utc.isoformat(), "unix": utc.timestamp(), "weekday": utc.strftime("%A")}


def calc(expr: str) -> dict:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        return {"error": f"Invalid expression: {exc}"}

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("Only + - * / ** % and numbers are allowed")

    try:
        value = ev(tree)
    except Exception as exc:
        return {"error": str(exc)}
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return {"error": "non-finite result"}
    return {"expression": expr, "result": value}


def weather(lat: float = 29.76, lon: float = -95.37, place: str = "Houston") -> dict:
    url = "https://api.open-meteo.com/v1/forecast"
    with httpx.Client(timeout=15.0, headers=UA) as client:
        resp = client.get(
            url,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return {"place": place, "current": data.get("current"), "source": "open-meteo"}


def wiki(query: str) -> dict:
    url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(query.replace(" ", "_"))
    with httpx.Client(timeout=15.0, headers={**UA, "Accept": "application/json"}, follow_redirects=True) as client:
        resp = client.get(url)
        if resp.status_code == 404:
            search = client.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "opensearch", "search": query, "limit": 1, "format": "json"},
            )
            hits = search.json()
            if len(hits) > 1 and hits[1]:
                return wiki(hits[1][0])
            return {"error": "No Wikipedia page"}
        resp.raise_for_status()
        data = resp.json()
    return {
        "title": data.get("title"),
        "extract": data.get("extract"),
        "url": (data.get("content_urls") or {}).get("desktop", {}).get("page"),
    }


def news(feed: str = "https://feeds.bbci.co.uk/news/rss.xml") -> dict:
    with httpx.Client(timeout=15.0, headers=UA, follow_redirects=True) as client:
        resp = client.get(feed)
        resp.raise_for_status()
    root = ET.fromstring(resp.text)
    items = []
    for item in root.findall(".//item")[:8]:
        items.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "pubDate": (item.findtext("pubDate") or "").strip(),
            }
        )
    return {"feed": feed, "items": items}


def dispatch(name: str, **kwargs) -> Any:
    if name == "now":
        return now()
    if name == "calc":
        return calc(kwargs.get("expression") or "0")
    if name == "weather":
        return weather(
            float(kwargs.get("lat") or 29.76),
            float(kwargs.get("lon") or -95.37),
            kwargs.get("place") or "Houston",
        )
    if name == "wiki":
        return wiki(kwargs.get("query") or "")
    if name == "news":
        return news(kwargs.get("feed") or "https://feeds.bbci.co.uk/news/rss.xml")
    return {"error": f"Unknown widget {name}"}
