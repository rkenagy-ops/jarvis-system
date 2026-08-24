"""Unrestricted open-source access: fetch, read, search and vendor ANY public repo.

github_oss.py only ever pulled READMEs from curated packs. This module removes that:
there is no allowlist and no starter pack — name any public repo and Jarvis gets the
actual source, not a summary of it.

    oss action=fetch  repo=pola-rs/polars        -> real source on disk
    oss action=tree   repo=pola-rs/polars        -> what's in it
    oss action=read   repo=... path=src/lib.rs   -> any file
    oss action=grep   repo=... pattern=fn main   -> search inside it
    oss action=search query=order book python    -> find repos to pull
    oss action=vendor repo=...                   -> copy into vendor/ to use
    oss action=ingest repo=...                   -> full source into the vault/RAG

The one thing that is NOT automatic is *executing* what gets pulled. `install` runs
pip against a fetched repo and takes a confirm_token, the same gate place_stock and
publer_schedule use. That is not a restriction on access — everything above is
unrestricted — it is because this process holds IBKR credentials and brokerage
session state, and silently running arbitrary setup.py from the internet in here is
how those get taken. Fetch freely; run deliberately.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

from . import config, guard, memory, obsidian

OSS_ROOT = config.ROOT / "workspace" / "oss"
VENDOR_ROOT = config.ROOT / "vendor"
MAX_TARBALL_BYTES = 250 * 1024 * 1024
MAX_READ_BYTES = 400_000
GREP_MAX_HITS = 200
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".mypy_cache"}
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar", ".whl",
    ".so", ".dylib", ".dll", ".exe", ".bin", ".o", ".a", ".class", ".jar", ".woff", ".woff2",
}

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _slug(repo: str) -> str:
    return repo.replace("/", "__")


def _repo_dir(repo: str) -> Path:
    return OSS_ROOT / _slug(repo)


def _valid(repo: str) -> bool:
    repo = (repo or "").strip()
    if not REPO_RE.match(repo):
        return False
    # "." is legal inside a repo name but ".." as a whole segment is not — it would
    # otherwise sail through the regex ("../etc" -> owner "..", name "etc").
    return all(seg not in {".", ".."} for seg in repo.split("/"))


def _safe_join(root: Path, relative: str) -> Path | None:
    """Resolve `relative` under `root`, refusing anything that escapes it."""
    target = (root / relative).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


# --------------------------------------------------------------------------- fetch


def fetch(repo: str, ref: str = "", *, force: bool = False) -> dict[str, Any]:
    """Download any public repo's source. No allowlist."""
    repo = (repo or "").strip().strip("/")
    if not _valid(repo):
        return {"error": "repo must look like owner/name."}

    dest = _repo_dir(repo)
    if dest.exists() and not force:
        files = sum(1 for _ in _walk(dest))
        return {"ok": True, "repo": repo, "path": str(dest), "files": files, "cached": True}

    refs = [ref] if ref else ["HEAD"]
    last_error = ""
    for candidate in refs:
        url = f"https://codeload.github.com/{repo}/tar.gz/{candidate}"
        try:
            resp = guard.fetch_public(url, timeout=120.0)
        except Exception as exc:
            last_error = str(exc)[:200]
            continue
        if resp.status_code >= 400:
            last_error = f"{resp.status_code} for ref {candidate}"
            continue
        blob = resp.content
        if len(blob) > MAX_TARBALL_BYTES:
            return {"error": f"{repo} is {len(blob) // 1024 // 1024}MB, over the {MAX_TARBALL_BYTES // 1024 // 1024}MB cap."}

        staging = dest.with_suffix(".incoming")
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
                # filter="data" refuses absolute paths, "..", symlinks out of tree,
                # devices and setuid bits — i.e. tar-slip.
                tar.extractall(staging, filter="data")
        except Exception as exc:
            shutil.rmtree(staging, ignore_errors=True)
            return {"error": f"extract failed: {str(exc)[:200]}"}

        # GitHub tarballs nest everything under one <repo>-<sha>/ directory.
        entries = [p for p in staging.iterdir() if p.is_dir()]
        root = entries[0] if len(entries) == 1 else staging

        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root), str(dest))
        shutil.rmtree(staging, ignore_errors=True)

        files = sum(1 for _ in _walk(dest))
        memory.remember(
            f"Fetched open-source repo {repo} ({files} files) to {dest}",
            kind="oss",
            tags=["oss", "fetch"],
        )
        return {"ok": True, "repo": repo, "path": str(dest), "files": files, "cached": False}

    return {"error": f"Could not fetch {repo}: {last_error}"}


def _walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


# --------------------------------------------------------------------------- read


def tree(repo: str, limit: int = 300, subdir: str = "") -> dict[str, Any]:
    root = _repo_dir(repo)
    if not root.exists():
        return {"error": f"{repo} not fetched yet. Run oss action=fetch repo={repo}."}
    base = _safe_join(root, subdir) if subdir else root
    if base is None or not base.exists():
        return {"error": f"No such path in {repo}: {subdir}"}
    rows = []
    for path in _walk(base):
        try:
            rows.append({"path": str(path.relative_to(root)), "bytes": path.stat().st_size})
        except OSError:
            continue
        if len(rows) >= limit:
            break
    rows.sort(key=lambda r: r["path"])
    return {"ok": True, "repo": repo, "count": len(rows), "files": rows}


def read(repo: str, path: str) -> dict[str, Any]:
    root = _repo_dir(repo)
    if not root.exists():
        return {"error": f"{repo} not fetched yet."}
    target = _safe_join(root, path)
    if target is None:
        return {"error": "Path escapes the repository."}
    if not target.is_file():
        return {"error": f"No such file: {path}"}
    if target.suffix.lower() in BINARY_SUFFIXES:
        return {"error": f"{path} looks binary.", "bytes": target.stat().st_size}
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"error": str(exc)[:200]}
    truncated = len(text) > MAX_READ_BYTES
    return {
        "ok": True,
        "repo": repo,
        "path": path,
        "truncated": truncated,
        "text": text[:MAX_READ_BYTES],
    }


def grep(repo: str, pattern: str, *, glob: str = "", ignore_case: bool = True) -> dict[str, Any]:
    root = _repo_dir(repo)
    if not root.exists():
        return {"error": f"{repo} not fetched yet."}
    if not pattern:
        return {"error": "pattern required."}
    try:
        rx = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error as exc:
        return {"error": f"bad regex: {exc}"}

    hits: list[dict[str, Any]] = []
    for path in _walk(root):
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        rel = str(path.relative_to(root))
        if glob and not Path(rel).match(glob):
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    if rx.search(line):
                        hits.append({"path": rel, "line": lineno, "text": line.rstrip()[:300]})
                        if len(hits) >= GREP_MAX_HITS:
                            return {"ok": True, "repo": repo, "hits": hits, "truncated": True}
        except OSError:
            continue
    return {"ok": True, "repo": repo, "hits": hits, "truncated": False}


# --------------------------------------------------------------------------- discover


def search(query: str, limit: int = 10) -> dict[str, Any]:
    """Find repos to pull. Any repo on GitHub, not a curated pack."""
    from . import github_client

    if not query:
        return {"error": "query required."}
    try:
        repos = github_client.search_repos(query, limit=limit)
    except Exception as exc:
        return {"error": str(exc)[:200]}
    return {
        "ok": True,
        "query": query,
        "repos": [
            {
                "repo": r.get("full_name"),
                "stars": r.get("stargazers_count"),
                "language": r.get("language"),
                "description": (r.get("description") or "")[:200],
                "url": r.get("html_url"),
                "license": ((r.get("license") or {}) or {}).get("spdx_id"),
            }
            for r in repos
        ],
        "next": "oss action=fetch repo=<owner/name> to pull the actual source.",
    }


# --------------------------------------------------------------------------- use


def vendor(repo: str, subdir: str = "") -> dict[str, Any]:
    """Copy fetched source into vendor/ so the running system can import it."""
    root = _repo_dir(repo)
    if not root.exists():
        return {"error": f"{repo} not fetched yet."}
    src = _safe_join(root, subdir) if subdir else root
    if src is None or not src.exists():
        return {"error": f"No such path in {repo}: {subdir}"}
    dest = VENDOR_ROOT / _slug(repo)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*SKIP_DIRS))
    return {"ok": True, "repo": repo, "vendored": str(dest)}


def ingest(repo: str, max_files: int = 40) -> dict[str, Any]:
    """Full source into the vault — not just the README."""
    root = _repo_dir(repo)
    if not root.exists():
        fetched = fetch(repo)
        if not fetched.get("ok"):
            return fetched

    listing = tree(repo, limit=max_files * 4)
    if not listing.get("ok"):
        return listing

    interesting = [
        f
        for f in listing["files"]
        if Path(f["path"]).suffix.lower() in {".py", ".md", ".ts", ".js", ".rs", ".go", ".toml", ".yaml", ".yml"}
    ][:max_files]

    chunks = []
    for entry in interesting:
        got = read(repo, entry["path"])
        if got.get("ok"):
            chunks.append(f"### `{entry['path']}`\n\n```\n{got['text'][:4000]}\n```")

    body = f"""---
type: source
repo: {repo}
---

# {repo}

Full-source ingest ({len(chunks)} files). Fetched to `workspace/oss/{_slug(repo)}`.

{chr(10).join(chunks)}
"""
    written = obsidian.write_note(f"Sources/oss/{_slug(repo)}.md", body)
    return {"ok": True, "repo": repo, "files_ingested": len(chunks), "vault": written.get("path")}


def install(repo: str = "", package: str = "", *, confirm_token: str | None = None) -> dict[str, Any]:
    """pip install a fetched repo or a named package.

    Gated the same way live orders are. Access to source is unrestricted; running it
    inside the process that holds the brokerage session is a deliberate act.
    """
    target = (repo or package or "").strip()
    if not target:
        return {"error": "repo or package required."}

    if not confirm_token:
        pending = memory.create_pending(
            "oss_install",
            {"repo": repo, "package": package},
            ttl_sec=300,
        )
        return {
            "blocked": True,
            "reason": (
                f"Installing {target} runs its setup code in the process that holds your IBKR "
                "session. Confirm to proceed."
            ),
            **pending,
        }
    used = memory.consume_pending(confirm_token)
    if not used or used.get("kind") != "oss_install":
        return {"error": "Invalid or expired confirm token. Nothing installed."}
    payload = used.get("payload") or {}
    repo = payload.get("repo") or repo
    package = payload.get("package") or package

    if repo:
        root = _repo_dir(repo)
        if not root.exists():
            return {"error": f"{repo} not fetched yet."}
        spec = str(root)
    else:
        spec = package

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", spec],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except Exception as exc:
        return {"error": str(exc)[:300]}
    return {
        "ok": proc.returncode == 0,
        "target": spec,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }


def status() -> dict[str, Any]:
    fetched = []
    if OSS_ROOT.exists():
        for entry in sorted(OSS_ROOT.iterdir()):
            if entry.is_dir():
                fetched.append({"repo": entry.name.replace("__", "/"), "path": str(entry)})
    return {
        "ok": True,
        "root": str(OSS_ROOT),
        "fetched": fetched,
        "count": len(fetched),
        "allowlist": None,
        "note": "Any public repo. No allowlist. install requires confirm_token.",
    }


def dispatch(action: str = "status", **kwargs: Any) -> Any:
    act = (action or "status").lower()
    repo = str(kwargs.get("repo") or "")
    if act in {"status", "list"}:
        return status()
    if act == "fetch":
        return fetch(repo, str(kwargs.get("ref") or ""), force=bool(kwargs.get("force")))
    if act in {"tree", "ls"}:
        return tree(repo, int(kwargs.get("limit") or 300), str(kwargs.get("subdir") or ""))
    if act in {"read", "cat"}:
        return read(repo, str(kwargs.get("path") or ""))
    if act in {"grep", "find"}:
        return grep(
            repo,
            str(kwargs.get("pattern") or kwargs.get("query") or ""),
            glob=str(kwargs.get("glob") or ""),
        )
    if act == "search":
        return search(str(kwargs.get("query") or ""), int(kwargs.get("limit") or 10))
    if act == "vendor":
        return vendor(repo, str(kwargs.get("subdir") or ""))
    if act == "ingest":
        return ingest(repo, int(kwargs.get("max_files") or 40))
    if act == "install":
        return install(
            repo=repo,
            package=str(kwargs.get("package") or ""),
            confirm_token=kwargs.get("confirm_token"),
        )
    return {
        "error": f"unknown oss action {act}",
        "actions": ["status", "search", "fetch", "tree", "read", "grep", "vendor", "ingest", "install"],
    }
