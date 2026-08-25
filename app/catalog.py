"""Free/open public APIs Jarvis can call without paid keys.

Each source is a real HTTP adapter. Optional keys (NASA) use public demo defaults.
"""

from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET

import httpx

UA = {
    "User-Agent": "SuperJarvis/2.2 (https://github.com/rkenagy-ops/jarvis-system; research)",
    "Accept": "application/json",
}


def _get(url: str, *, params: dict | None = None, headers: dict | None = None, timeout: float = 20.0, text: bool = False) -> Any:
    hdrs = {**UA, **(headers or {})}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=hdrs) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        if text or "json" not in (resp.headers.get("content-type") or ""):
            return resp.text[:20000]
        return resp.json()


def _http_ok(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in {"http", "https"} and bool(p.netloc)


def arxiv(query: str, limit: int = 5) -> dict:
    xml = _get(
        "https://export.arxiv.org/api/query",
        params={"search_query": f"all:{query}", "start": 0, "max_results": min(limit, 8)},
        text=True,
    )
    root = ET.fromstring(xml)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    papers = []
    for entry in root.findall("a:entry", ns)[:limit]:
        papers.append(
            {
                "title": (entry.findtext("a:title", default="", namespaces=ns) or "").strip(),
                "summary": (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()[:600],
                "url": entry.findtext("a:id", default="", namespaces=ns),
                "published": (entry.findtext("a:published", default="", namespaces=ns) or "")[:10],
            }
        )
    return {"source": "arxiv", "query": query, "results": papers}


def semantic_scholar(query: str, limit: int = 5) -> dict:
    data = _get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={"query": query, "limit": min(limit, 8), "fields": "title,year,abstract,url,citationCount,authors"},
    )
    out = []
    for p in data.get("data") or []:
        authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:3])
        out.append(
            {
                "title": p.get("title"),
                "year": p.get("year"),
                "citations": p.get("citationCount"),
                "authors": authors,
                "url": p.get("url"),
                "abstract": (p.get("abstract") or "")[:500],
            }
        )
    return {"source": "semantic_scholar", "results": out}


def pubmed(query: str, limit: int = 5) -> dict:
    found = _get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={"db": "pubmed", "term": query, "retmode": "json", "retmax": min(limit, 8)},
    )
    ids = ((found.get("esearchresult") or {}).get("idlist")) or []
    if not ids:
        return {"source": "pubmed", "results": []}
    summary = _get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
        params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
    )
    out = []
    for pid in ids:
        rec = (summary.get("result") or {}).get(pid) or {}
        out.append({"id": pid, "title": rec.get("title"), "source": rec.get("fulljournalname"), "date": rec.get("pubdate")})
    return {"source": "pubmed", "results": out}


def hackernews(query: str, limit: int = 6) -> dict:
    data = _get("https://hn.algolia.com/api/v1/search", params={"query": query, "hitsPerPage": min(limit, 10)})
    hits = [
        {"title": h.get("title"), "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}", "points": h.get("points")}
        for h in data.get("hits") or []
    ]
    return {"source": "hackernews", "results": hits}


def stackoverflow(query: str, limit: int = 5) -> dict:
    data = _get(
        "https://api.stackexchange.com/2.3/search/advanced",
        params={"order": "desc", "sort": "relevance", "q": query, "site": "stackoverflow", "pagesize": min(limit, 8)},
    )
    items = [
        {"title": i.get("title"), "score": i.get("score"), "url": i.get("link"), "answered": i.get("is_answered")}
        for i in data.get("items") or []
    ]
    return {"source": "stackoverflow", "results": items}


def gutenberg(query: str) -> dict:
    data = _get("https://gutendex.com/books", params={"search": query})
    books = [
        {"title": b.get("title"), "authors": [a.get("name") for a in b.get("authors") or []], "id": b.get("id")}
        for b in (data.get("results") or [])[:6]
    ]
    return {"source": "gutenberg", "results": books}


def open_library(query: str) -> dict:
    data = _get("https://openlibrary.org/search.json", params={"q": query, "limit": 6})
    docs = [
        {"title": d.get("title"), "author": (d.get("author_name") or [None])[0], "year": d.get("first_publish_year")}
        for d in data.get("docs") or []
    ][:6]
    return {"source": "open_library", "results": docs}


_LANG = {
    "spanish": "es", "french": "fr", "german": "de", "italian": "it", "portuguese": "pt",
    "chinese": "zh", "japanese": "ja", "korean": "ko", "arabic": "ar", "hindi": "hi",
    "russian": "ru", "dutch": "nl", "swedish": "sv", "english": "en",
}


def translate(query: str) -> dict:
    text = (query or "").strip()
    dest = "es"
    low = text.lower()
    m = re.search(r"\bto\s+([a-z]{2,12})\b", low)
    if m:
        token = m.group(1)
        dest = _LANG.get(token, token if len(token) == 2 else "es")
        text = re.sub(r"\bto\s+[a-z]{2,12}\b", "", text, flags=re.I).strip()
    if "|" in text:
        text, dest = [p.strip() for p in text.split("|", 1)]
    if not text:
        return {"error": "nothing to translate"}
    data = _get(
        "https://api.mymemory.translated.net/get",
        params={"q": text[:500], "langpair": f"en|{dest}"},
    )
    resp = data.get("responseData") or {}
    return {
        "source": "mymemory",
        "from": "en",
        "to": dest,
        "text": text,
        "translated": resp.get("translatedText"),
    }


def dictionary(query: str) -> dict:
    data = _get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote(query)}")
    if isinstance(data, dict) and data.get("title"):
        return {"error": data.get("title"), "query": query}
    entry = data[0] if isinstance(data, list) and data else {}
    meanings = []
    for m in (entry.get("meanings") or [])[:3]:
        defs = [d.get("definition") for d in (m.get("definitions") or [])[:2]]
        meanings.append({"part": m.get("partOfSpeech"), "defs": defs})
    return {"source": "dictionary", "word": entry.get("word") or query, "meanings": meanings}


def wikidata(query: str) -> dict:
    data = _get(
        "https://www.wikidata.org/w/api.php",
        params={"action": "wbsearchentities", "search": query, "language": "en", "format": "json"},
    )
    hits = [{"id": i.get("id"), "label": i.get("label"), "desc": i.get("description")} for i in data.get("search") or []][:8]
    return {"source": "wikidata", "results": hits}


def jina_read(url: str) -> dict:
    if not _http_ok(url):
        return {"error": "Only http(s) URLs"}
    text = _get("https://r.jina.ai/" + url, headers={"Accept": "text/plain"}, text=True, timeout=30.0)
    return {"source": "jina", "url": url, "text": text[:12000]}


def duckduckgo(query: str) -> dict:
    data = _get("https://api.duckduckgo.com/", params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1})
    related = [t.get("Text") for t in (data.get("RelatedTopics") or []) if isinstance(t, dict) and t.get("Text")][:6]
    return {
        "source": "duckduckgo",
        "heading": data.get("Heading"),
        "abstract": data.get("AbstractText"),
        "url": data.get("AbstractURL"),
        "related": related,
    }


def archive_search(query: str) -> dict:
    data = _get(
        "https://archive.org/advancedsearch.php",
        params={"q": query, "fl": "identifier,title,year", "output": "json", "rows": 6},
    )
    docs = (data.get("response") or {}).get("docs") or []
    return {"source": "archive.org", "results": docs}


def fx(query: str = "USD") -> dict:
    parts = [p.strip().upper() for p in query.replace("to", " ").replace("/", " ").split() if p.strip()]
    base = parts[0] if parts else "USD"
    symbols = ",".join(parts[1:]) if len(parts) > 1 else None
    params = {"from": base}
    if symbols:
        params["to"] = symbols
    data = _get("https://api.frankfurter.app/latest", params=params)
    return {"source": "frankfurter", "base": data.get("base"), "date": data.get("date"), "rates": data.get("rates")}


def fear_greed(_: str = "") -> dict:
    data = _get("https://api.alternative.me/fng/", params={"limit": 3})
    return {"source": "fear_greed", "data": data.get("data")}


def defillama(query: str) -> dict:
    q = (query or "protocols").strip().lower()
    if q in {"chains", "tvl"}:
        data = _get("https://api.llama.fi/v2/chains")
        top = sorted(data, key=lambda r: r.get("tvl") or 0, reverse=True)[:8]
        return {"source": "defillama", "chains": [{"name": c.get("name"), "tvl": c.get("tvl")} for c in top]}
    proto = q.replace(" ", "-")
    try:
        data = _get(f"https://api.llama.fi/protocol/{proto}")
        return {"source": "defillama", "name": data.get("name"), "tvl": data.get("tvl"), "category": data.get("category"), "url": data.get("url")}
    except Exception:
        data = _get("https://api.llama.fi/protocols")
        hits = [p for p in data if proto in (p.get("name") or "").lower() or proto in (p.get("slug") or "")][:6]
        return {"source": "defillama", "matches": [{"name": p.get("name"), "tvl": p.get("tvl"), "slug": p.get("slug")} for p in hits]}


def coingecko(query: str) -> dict:
    data = _get("https://api.coingecko.com/api/v3/search", params={"query": query})
    coins = [{"id": c.get("id"), "name": c.get("name"), "symbol": c.get("symbol")} for c in (data.get("coins") or [])[:8]]
    return {"source": "coingecko", "coins": coins}


def polymarket(query: str) -> dict:
    from . import poly

    q = (query or "").strip()
    if q.lower() in {"bounce", "rotate", "hot"}:
        return poly.bounce()
    return poly.scan(query=q, limit=10)


def sec_edgar(query: str) -> dict:
    data = _get(
        "https://efts.sec.gov/LATEST/search-index",
        params={"q": query, "dateRange": "custom", "startdt": "2024-01-01"},
        headers={"User-Agent": UA["User-Agent"]},
    )
    hits = []
    for h in ((data.get("hits") or {}).get("hits") or [])[:6]:
        src = h.get("_source") or {}
        hits.append(
            {
                "entity": (src.get("entity_name") or src.get("display_names") or [""])[0] if isinstance(src.get("display_names"), list) else src.get("entity_name"),
                "form": src.get("form"),
                "filed": src.get("file_date"),
                "id": h.get("_id"),
            }
        )
    return {"source": "sec_edgar", "results": hits}


def geocode(query: str) -> dict:
    data = _get("https://nominatim.openstreetmap.org/search", params={"q": query, "format": "json", "limit": 4})
    return {"source": "nominatim", "results": [{"name": r.get("display_name"), "lat": r.get("lat"), "lon": r.get("lon")} for r in data]}


def countries(query: str) -> dict:
    data = _get(f"https://restcountries.com/v3.1/name/{quote(query)}")
    out = []
    for c in data[:5] if isinstance(data, list) else []:
        out.append(
            {
                "name": (c.get("name") or {}).get("common"),
                "capital": (c.get("capital") or [None])[0],
                "region": c.get("region"),
                "population": c.get("population"),
                "currencies": list((c.get("currencies") or {}).keys()),
            }
        )
    return {"source": "restcountries", "results": out}


def holidays(query: str = "US") -> dict:
    year = "2026"
    code = "US"
    for part in query.replace(",", " ").split():
        if part.isdigit() and len(part) == 4:
            year = part
        elif part.isalpha() and len(part) == 2:
            code = part.upper()
    data = _get(f"https://date.nager.at/api/v3/PublicHolidays/{year}/{code}")
    items = [{"date": d.get("date"), "name": d.get("localName")} for d in data[:20]] if isinstance(data, list) else []
    return {"source": "nager", "year": year, "country": code, "holidays": items}


def earthquakes(query: str = "week") -> dict:
    # The chosen feed was computed and then dropped, so every call hit the same
    # generic endpoint and "significant" returned the same thing as "day".
    feed = "significant_week" if "sig" in query or "week" in query else "4.5_day"
    data = _get(f"https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{feed}.geojson")
    feats = []
    for f in (data.get("features") or [])[:8]:
        p = f.get("properties") or {}
        feats.append({"mag": p.get("mag"), "place": p.get("place"), "time": p.get("time"), "url": p.get("url")})
    return {"source": "usgs", "events": feats}


def nws_alerts(query: str = "TX") -> dict:
    area = (query or "TX").strip().upper()[:2]
    data = _get("https://api.weather.gov/alerts/active", params={"area": area}, headers={"Accept": "application/geo+json"})
    alerts = []
    for f in (data.get("features") or [])[:8]:
        p = f.get("properties") or {}
        alerts.append({"event": p.get("event"), "headline": p.get("headline"), "severity": p.get("severity")})
    return {"source": "nws", "area": area, "alerts": alerts}


def pypi(query: str) -> dict:
    try:
        data = _get(f"https://pypi.org/pypi/{quote(query)}/json")
        info = data.get("info") or {}
        return {"source": "pypi", "name": info.get("name"), "version": info.get("version"), "summary": info.get("summary"), "home": info.get("home_page")}
    except Exception:
        data = _get("https://pypi.org/search/", params={"q": query}, text=True)
        names = re.findall(r'href="/project/([^/]+)/"', data)[:8]
        return {"source": "pypi", "matches": list(dict.fromkeys(names))}


def npm(query: str) -> dict:
    try:
        data = _get(f"https://registry.npmjs.org/{quote(query)}")
        latest = (data.get("dist-tags") or {}).get("latest")
        desc = ((data.get("versions") or {}).get(latest) or {}).get("description") if latest else data.get("description")
        return {"source": "npm", "name": data.get("name"), "latest": latest, "description": desc}
    except Exception:
        data = _get("https://registry.npmjs.org/-/v1/search", params={"text": query, "size": 6})
        return {"source": "npm", "matches": [{"name": o.get("package", {}).get("name"), "desc": o.get("package", {}).get("description")} for o in data.get("objects") or []]}


def crates(query: str) -> dict:
    data = _get("https://crates.io/api/v1/crates", params={"q": query, "per_page": 6})
    crates_ = [{"name": c.get("name"), "downloads": c.get("downloads"), "desc": c.get("description")} for c in data.get("crates") or []]
    return {"source": "crates.io", "results": crates_}


def github_public(query: str) -> dict:
    data = _get("https://api.github.com/search/repositories", params={"q": query, "per_page": 5, "sort": "stars"})
    repos = [
        {"full_name": r.get("full_name"), "stars": r.get("stargazers_count"), "desc": r.get("description"), "url": r.get("html_url")}
        for r in data.get("items") or []
    ]
    return {"source": "github", "results": repos}


def cisa_kev(query: str = "") -> dict:
    data = _get("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json", timeout=40.0)
    vulns = data.get("vulnerabilities") or []
    q = (query or "").lower()
    if q:
        vulns = [v for v in vulns if q in (v.get("cveID") or "").lower() or q in (v.get("vulnerabilityName") or "").lower() or q in (v.get("vendorProject") or "").lower()]
    out = [
        {"cve": v.get("cveID"), "name": v.get("vulnerabilityName"), "vendor": v.get("vendorProject"), "due": v.get("dueDate")}
        for v in vulns[:8]
    ]
    return {"source": "cisa_kev", "count": len(out), "results": out}


def cve_lookup(query: str) -> dict:
    cve = query.strip().upper()
    if not cve.startswith("CVE-"):
        return cisa_kev(query)
    try:
        data = _get(f"https://cve.circl.lu/api/cve/{cve}")
        return {"source": "circl", "id": data.get("id") or cve, "summary": (data.get("summary") or data.get("containers", {}).get("cna", {}).get("title")), "raw_keys": list(data)[:12]}
    except Exception as exc:
        return {"error": str(exc), "hint": "Pass a CVE-YYYY-NNNN id or a vendor name for CISA KEV"}


def crtsh(query: str) -> dict:
    data = _get("https://crt.sh/", params={"q": query, "output": "json"})
    if not isinstance(data, list):
        return {"source": "crt.sh", "results": []}
    names = []
    for row in data[:20]:
        name = row.get("common_name") or row.get("name_value")
        if name and name not in names:
            names.append(name)
    return {"source": "crt.sh", "names": names[:15]}


def rdap(query: str) -> dict:
    target = query.strip()
    kind = "domain"
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", target):
        kind = "ip"
    data = _get(f"https://rdap.org/{kind}/{quote(target)}")
    return {
        "source": "rdap",
        "handle": data.get("handle"),
        "name": data.get("ldhName") or data.get("name"),
        "status": data.get("status"),
        "type": data.get("objectClassName"),
    }


def ip_lookup(query: str = "") -> dict:
    path = query.strip() or ""
    url = f"http://ip-api.com/json/{path}" if path else "http://ip-api.com/json/"
    data = _get(url)
    return {"source": "ip-api", "query": data.get("query"), "country": data.get("country"), "city": data.get("city"), "isp": data.get("isp"), "org": data.get("org")}


def nasa_apod(_: str = "") -> dict:
    data = _get("https://api.nasa.gov/planetary/apod", params={"api_key": "DEMO_KEY"})
    return {"source": "nasa_apod", "title": data.get("title"), "date": data.get("date"), "url": data.get("url"), "explanation": (data.get("explanation") or "")[:800]}


def worldbank(query: str = "US GDP") -> dict:
    code = "US"
    indicator = "NY.GDP.MKTP.CD"
    if "pop" in query.lower():
        indicator = "SP.POP.TOTL"
    for part in query.replace(",", " ").split():
        if part.isalpha() and len(part) == 2:
            code = part.upper()
    data = _get(
        f"https://api.worldbank.org/v2/country/{code}/indicator/{indicator}",
        params={"format": "json", "per_page": 6},
    )
    rows = data[1] if isinstance(data, list) and len(data) > 1 else []
    series = [{"year": r.get("date"), "value": r.get("value")} for r in rows if r.get("value") is not None]
    return {"source": "worldbank", "country": code, "indicator": indicator, "series": series}


def musicbrainz(query: str) -> dict:
    data = _get("https://musicbrainz.org/ws/2/artist/", params={"query": query, "fmt": "json"})
    artists = [{"name": a.get("name"), "country": a.get("country"), "id": a.get("id")} for a in data.get("artists") or []][:6]
    return {"source": "musicbrainz", "artists": artists}


def openfoodfacts(query: str) -> dict:
    if query.isdigit():
        data = _get(f"https://world.openfoodfacts.org/api/v2/product/{query}.json")
        p = data.get("product") or {}
        return {"source": "openfoodfacts", "name": p.get("product_name"), "brands": p.get("brands"), "nutriscore": p.get("nutriscore_grade")}
    data = _get("https://world.openfoodfacts.org/cgi/search.pl", params={"search_terms": query, "search_simple": 1, "action": "process", "json": 1, "page_size": 5})
    products = [{"name": p.get("product_name"), "brands": p.get("brands")} for p in data.get("products") or []]
    return {"source": "openfoodfacts", "results": products}


SOURCES: dict[str, tuple[str, Callable[..., dict]]] = {
    "arxiv": ("Research papers (arXiv)", arxiv),
    "semantic_scholar": ("Academic papers + citations", semantic_scholar),
    "pubmed": ("Biomedical literature (NCBI)", pubmed),
    "hackernews": ("Hacker News via Algolia", hackernews),
    "stackoverflow": ("Stack Overflow Q&A", stackoverflow),
    "gutenberg": ("Project Gutenberg books", gutenberg),
    "open_library": ("Open Library catalog", open_library),
    "dictionary": ("English definitions", dictionary),
    "translate": ("Free translation (MyMemory)", translate),
    "wikidata": ("Wikidata entities", wikidata),
    "jina": ("Clean webpage extract (Jina Reader)", jina_read),
    "duckduckgo": ("Instant answers", duckduckgo),
    "archive": ("Internet Archive search", archive_search),
    "fx": ("ECB FX via Frankfurter", fx),
    "fear_greed": ("Crypto fear & greed", fear_greed),
    "defillama": ("Crypto TVL", defillama),
    "coingecko": ("Coin search", coingecko),
    "sec_edgar": ("SEC EDGAR filings", sec_edgar),
    "polymarket": ("Polymarket public prediction markets (Gamma)", polymarket),
    "geocode": ("OpenStreetMap Nominatim", geocode),
    "countries": ("REST Countries", countries),
    "holidays": ("Public holidays (Nager)", holidays),
    "earthquakes": ("USGS earthquakes", earthquakes),
    "nws": ("US NWS alerts", nws_alerts),
    "pypi": ("Python packages", pypi),
    "npm": ("npm packages", npm),
    "crates": ("Rust crates", crates),
    "github": ("Public GitHub repo search", github_public),
    "cisa_kev": ("CISA known exploited vulns", cisa_kev),
    "cve": ("CVE lookup (CIRCL / KEV)", cve_lookup),
    "crtsh": ("Certificate transparency", crtsh),
    "rdap": ("Domain / IP RDAP", rdap),
    "ip": ("IP geolocation", ip_lookup),
    "nasa": ("NASA Astronomy Picture of the Day", nasa_apod),
    "worldbank": ("World Bank indicators", worldbank),
    "musicbrainz": ("MusicBrainz artists", musicbrainz),
    "openfoodfacts": ("Open Food Facts", openfoodfacts),
}


def list_sources() -> list[dict]:
    return [{"id": k, "desc": v[0]} for k, v in SOURCES.items()]


def call(source: str, query: str = "", **kwargs) -> dict:
    src = (source or "").strip().lower()
    if src not in SOURCES:
        return {"error": f"Unknown source {source}", "sources": [s["id"] for s in list_sources()]}
    q = query or kwargs.get("url") or kwargs.get("symbol") or kwargs.get("q") or ""
    try:
        return SOURCES[src][1](q)
    except Exception as exc:
        return {"source": src, "error": str(exc)}
