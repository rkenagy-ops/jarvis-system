from __future__ import annotations

import base64
from typing import Any

import httpx

from . import config

UA = "SuperJarvis/1.0"


class GitHubError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not config.GITHUB_TOKEN:
        raise GitHubError("GITHUB_TOKEN is not set. Add a GitHub personal access token in Settings.")
    return {
        "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": UA,
    }


def _request(method: str, path: str, **kwargs) -> Any:
    url = path if path.startswith("http") else f"{config.GITHUB_API}{path}"
    with httpx.Client(timeout=40.0) as client:
        resp = client.request(method, url, headers=_headers(), **kwargs)
    if resp.status_code >= 400:
        raise GitHubError(f"GitHub {resp.status_code}: {resp.text[:800]}")
    if resp.status_code == 204 or not resp.content:
        return {"ok": True, "status": resp.status_code}
    return resp.json()


def whoami() -> dict:
    user = _request("GET", "/user")
    config.GITHUB_USERNAME = user.get("login") or config.GITHUB_USERNAME
    return {
        "login": user.get("login"),
        "name": user.get("name"),
        "id": user.get("id"),
        "html_url": user.get("html_url"),
        "public_repos": user.get("public_repos"),
        "total_private_repos": user.get("total_private_repos"),
        "plan": (user.get("plan") or {}).get("name"),
    }


def list_repos(limit: int = 20, visibility: str = "all") -> list[dict]:
    data = _request(
        "GET",
        "/user/repos",
        params={"per_page": min(limit, 100), "sort": "updated", "visibility": visibility},
    )
    return [
        {
            "full_name": r.get("full_name"),
            "private": r.get("private"),
            "description": r.get("description"),
            "html_url": r.get("html_url"),
            "default_branch": r.get("default_branch"),
            "language": r.get("language"),
            "pushed_at": r.get("pushed_at"),
            "stargazers_count": r.get("stargazers_count"),
            "open_issues_count": r.get("open_issues_count"),
        }
        for r in data
    ]


def get_repo(owner: str, repo: str) -> dict:
    r = _request("GET", f"/repos/{owner}/{repo}")
    return {
        "full_name": r.get("full_name"),
        "description": r.get("description"),
        "html_url": r.get("html_url"),
        "default_branch": r.get("default_branch"),
        "language": r.get("language"),
        "topics": r.get("topics"),
        "open_issues_count": r.get("open_issues_count"),
        "private": r.get("private"),
    }


def list_issues(owner: str, repo: str, state: str = "open", limit: int = 20) -> list[dict]:
    data = _request(
        "GET",
        f"/repos/{owner}/{repo}/issues",
        params={"state": state, "per_page": min(limit, 100)},
    )
    return [
        {
            "number": i.get("number"),
            "title": i.get("title"),
            "state": i.get("state"),
            "user": (i.get("user") or {}).get("login"),
            "html_url": i.get("html_url"),
            "pull_request": bool(i.get("pull_request")),
            "labels": [lb.get("name") for lb in i.get("labels") or []],
        }
        for i in data
        if not i.get("pull_request")
    ]


def create_issue(owner: str, repo: str, title: str, body: str = "", labels: list[str] | None = None) -> dict:
    payload: dict[str, Any] = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels
    i = _request("POST", f"/repos/{owner}/{repo}/issues", json=payload)
    return {"number": i.get("number"), "html_url": i.get("html_url"), "title": i.get("title")}


def comment_issue(owner: str, repo: str, number: int, body: str) -> dict:
    c = _request("POST", f"/repos/{owner}/{repo}/issues/{number}/comments", json={"body": body})
    return {"id": c.get("id"), "html_url": c.get("html_url")}


def list_pulls(owner: str, repo: str, state: str = "open", limit: int = 20) -> list[dict]:
    data = _request(
        "GET",
        f"/repos/{owner}/{repo}/pulls",
        params={"state": state, "per_page": min(limit, 100)},
    )
    return [
        {
            "number": p.get("number"),
            "title": p.get("title"),
            "state": p.get("state"),
            "user": (p.get("user") or {}).get("login"),
            "html_url": p.get("html_url"),
            "draft": p.get("draft"),
            "head": (p.get("head") or {}).get("ref"),
            "base": (p.get("base") or {}).get("ref"),
        }
        for p in data
    ]


def get_file(owner: str, repo: str, path: str, ref: str | None = None) -> dict:
    params = {"ref": ref} if ref else None
    data = _request("GET", f"/repos/{owner}/{repo}/contents/{path.lstrip('/')}", params=params)
    if isinstance(data, list):
        return {
            "type": "dir",
            "path": path,
            "entries": [{"name": e.get("name"), "type": e.get("type"), "path": e.get("path")} for e in data],
        }
    content = ""
    if data.get("encoding") == "base64" and data.get("content"):
        raw = base64.b64decode(data["content"])
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = f"[binary {len(raw)} bytes]"
    if len(content) > 20000:
        content = content[:20000] + "\n...[truncated]"
    return {"type": "file", "path": data.get("path"), "html_url": data.get("html_url"), "content": content}


def search_code(query: str, limit: int = 10) -> list[dict]:
    data = _request("GET", "/search/code", params={"q": query, "per_page": min(limit, 30)})
    return [
        {
            "repository": (i.get("repository") or {}).get("full_name"),
            "path": i.get("path"),
            "html_url": i.get("html_url"),
        }
        for i in data.get("items", [])
    ]


def search_issues(query: str, limit: int = 10) -> list[dict]:
    data = _request("GET", "/search/issues", params={"q": query, "per_page": min(limit, 30)})
    return [
        {
            "title": i.get("title"),
            "html_url": i.get("html_url"),
            "state": i.get("state"),
            "repository": "/".join((i.get("repository_url") or "").split("/")[-2:]),
        }
        for i in data.get("items", [])
    ]


def list_commits(owner: str, repo: str, limit: int = 10) -> list[dict]:
    data = _request("GET", f"/repos/{owner}/{repo}/commits", params={"per_page": min(limit, 30)})
    return [
        {
            "sha": c.get("sha", "")[:8],
            "message": ((c.get("commit") or {}).get("message") or "").split("\n", 1)[0],
            "author": ((c.get("commit") or {}).get("author") or {}).get("name"),
            "date": ((c.get("commit") or {}).get("author") or {}).get("date"),
            "html_url": c.get("html_url"),
        }
        for c in data
    ]


def create_repo(name: str, description: str = "", private: bool = True) -> dict:
    data = _request(
        "POST",
        "/user/repos",
        json={"name": name, "description": description, "private": private, "auto_init": True},
    )
    return {"full_name": data.get("full_name"), "html_url": data.get("html_url"), "private": data.get("private")}


def dispatch(action: str, **kwargs) -> Any:
    actions = {
        "whoami": lambda: whoami(),
        "list_repos": lambda: list_repos(int(kwargs.get("limit") or 20), kwargs.get("visibility") or "all"),
        "get_repo": lambda: get_repo(kwargs["owner"], kwargs["repo"]),
        "list_issues": lambda: list_issues(kwargs["owner"], kwargs["repo"], kwargs.get("state") or "open", int(kwargs.get("limit") or 20)),
        "create_issue": lambda: create_issue(kwargs["owner"], kwargs["repo"], kwargs["title"], kwargs.get("body") or "", kwargs.get("labels")),
        "comment_issue": lambda: comment_issue(kwargs["owner"], kwargs["repo"], int(kwargs["number"]), kwargs["body"]),
        "list_pulls": lambda: list_pulls(kwargs["owner"], kwargs["repo"], kwargs.get("state") or "open", int(kwargs.get("limit") or 20)),
        "get_file": lambda: get_file(kwargs["owner"], kwargs["repo"], kwargs["path"], kwargs.get("ref")),
        "search_code": lambda: search_code(kwargs["query"], int(kwargs.get("limit") or 10)),
        "search_issues": lambda: search_issues(kwargs["query"], int(kwargs.get("limit") or 10)),
        "list_commits": lambda: list_commits(kwargs["owner"], kwargs["repo"], int(kwargs.get("limit") or 10)),
        "create_repo": lambda: create_repo(kwargs["name"], kwargs.get("description") or "", bool(kwargs.get("private", True))),
    }
    if action not in actions:
        raise GitHubError(f"Unknown GitHub action: {action}")
    return actions[action]()
