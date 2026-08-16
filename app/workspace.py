from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path
from typing import Any

from . import config

MAX_READ = 200_000


def _root() -> Path:
    config.WORKSPACE_DIR.mkdir(exist_ok=True)
    return config.WORKSPACE_DIR.resolve()


def resolve(rel: str) -> Path:
    root = _root()
    path = (root / (rel or ".")).resolve()
    if path != root and root not in path.parents:
        raise ValueError("Path escapes workspace")
    return path


def list_files(rel: str = ".") -> dict:
    path = resolve(rel)
    if not path.exists():
        return {"error": "Not found", "path": rel}
    if path.is_file():
        return {"type": "file", "path": str(path.relative_to(_root())), "bytes": path.stat().st_size}
    entries = []
    for child in sorted(path.iterdir()):
        entries.append(
            {
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
                "bytes": child.stat().st_size if child.is_file() else None,
            }
        )
    return {"path": str(path.relative_to(_root())) if path != _root() else ".", "entries": entries}


def read_file(rel: str) -> dict:
    path = resolve(rel)
    if not path.is_file():
        return {"error": "Not a file"}
    data = path.read_bytes()[:MAX_READ]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"path": rel, "bytes": path.stat().st_size, "note": "binary file, not shown"}
    return {"path": rel, "bytes": path.stat().st_size, "text": text[:40000]}


def write_file(rel: str, content: str) -> dict:
    path = resolve(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"ok": True, "path": rel, "bytes": path.stat().st_size}


def analyze_file(rel: str) -> dict:
    path = resolve(rel)
    if not path.is_file():
        return {"error": "Not a file"}
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return _profile_rows(data, rel)
        return {"path": rel, "type": "json", "preview": str(data)[:2000]}
    if suffix in {".csv", ".tsv"}:
        delim = "\t" if suffix == ".tsv" else ","
        with path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh, delimiter=delim))
        return _profile_rows(rows, rel)
    text = path.read_text(encoding="utf-8", errors="replace")
    words = text.split()
    return {
        "path": rel,
        "type": "text",
        "chars": len(text),
        "words": len(words),
        "lines": text.count("\n") + 1,
        "preview": text[:1500],
    }


def _profile_rows(rows: list[dict], rel: str) -> dict:
    if not rows:
        return {"path": rel, "rows": 0}
    cols = list(rows[0].keys())
    profiles = {}
    for col in cols:
        vals = [r.get(col) for r in rows if r.get(col) not in (None, "")]
        nums = []
        for v in vals:
            try:
                nums.append(float(str(v).replace(",", "")))
            except ValueError:
                continue
        info: dict[str, Any] = {"non_empty": len(vals), "numeric": len(nums)}
        if nums:
            info.update(
                {
                    "min": min(nums),
                    "max": max(nums),
                    "mean": statistics.fmean(nums),
                    "stdev": statistics.pstdev(nums) if len(nums) > 1 else 0,
                }
            )
        else:
            uniq = sorted({str(v) for v in vals})
            info["unique"] = len(uniq)
            info["sample"] = uniq[:8]
        profiles[col] = info
    return {"path": rel, "rows": len(rows), "columns": cols, "profile": profiles, "head": rows[:5]}


def dispatch(action: str, **kwargs) -> Any:
    try:
        if action == "list":
            return list_files(kwargs.get("path") or ".")
        if action == "read":
            return read_file(kwargs.get("path") or "")
        if action == "write":
            return write_file(kwargs.get("path") or "", kwargs.get("content") or "")
        if action == "analyze":
            return analyze_file(kwargs.get("path") or "")
        return {"error": f"Unknown workspace action {action}"}
    except Exception as exc:
        return {"error": str(exc)}
