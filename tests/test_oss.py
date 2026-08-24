import io
import tarfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import oss


def test_repo_validation():
    assert oss._valid("pola-rs/polars")
    assert oss._valid("erdewit/ib_insync")
    assert not oss._valid("../etc")
    assert not oss._valid("nope")
    assert not oss._valid("a/b/c")
    assert not oss._valid("")


def test_safe_join_refuses_escape(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    assert oss._safe_join(root, "src/lib.rs") is not None
    assert oss._safe_join(root, "../../etc/passwd") is None
    assert oss._safe_join(root, "/etc/passwd") is None


def test_no_allowlist():
    """The whole point: any public repo, not a curated pack."""
    st = oss.status()
    assert st["allowlist"] is None


def test_dispatch_unknown():
    out = oss.dispatch("nope")
    assert "error" in out
    assert "fetch" in out["actions"]


def _make_repo(tmp_path, monkeypatch, files: dict[str, str]):
    root = tmp_path / "oss"
    monkeypatch.setattr(oss, "OSS_ROOT", root)
    repo_dir = root / oss._slug("acme/widget")
    repo_dir.mkdir(parents=True)
    for rel, body in files.items():
        target = repo_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return repo_dir


def test_tree_read_grep(tmp_path, monkeypatch):
    _make_repo(
        tmp_path,
        monkeypatch,
        {
            "main.py": "def main():\n    return 42\n",
            "src/util.py": "def helper():\n    pass\n",
            "README.md": "# widget\n",
        },
    )

    listing = oss.tree("acme/widget")
    assert listing["ok"]
    paths = {f["path"] for f in listing["files"]}
    assert "main.py" in paths and "src/util.py" in paths

    got = oss.read("acme/widget", "main.py")
    assert got["ok"] and "return 42" in got["text"]

    hits = oss.grep("acme/widget", r"def \w+")
    assert hits["ok"]
    assert {h["path"] for h in hits["hits"]} == {"main.py", "src/util.py"}


def test_read_refuses_traversal(tmp_path, monkeypatch):
    _make_repo(tmp_path, monkeypatch, {"main.py": "x = 1\n"})
    out = oss.read("acme/widget", "../../../etc/passwd")
    assert "error" in out
    assert "escapes" in out["error"].lower()


def test_read_unfetched_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(oss, "OSS_ROOT", tmp_path / "empty")
    out = oss.read("never/fetched", "x.py")
    assert "error" in out and "not fetched" in out["error"]


def test_grep_bad_regex(tmp_path, monkeypatch):
    _make_repo(tmp_path, monkeypatch, {"a.py": "x\n"})
    out = oss.grep("acme/widget", "(unclosed")
    assert "error" in out


def test_fetch_rejects_bad_repo():
    assert "error" in oss.fetch("not-a-repo")
    assert "error" in oss.fetch("../../evil")


def test_fetch_extracts_tarball(tmp_path, monkeypatch):
    """A GitHub tarball nests under <repo>-<sha>/; fetch should flatten that."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        payload = b"print('hi')\n"
        info = tarfile.TarInfo("widget-abc123/main.py")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    blob = buf.getvalue()

    class FakeResponse:
        status_code = 200
        content = blob

    monkeypatch.setattr(oss, "OSS_ROOT", tmp_path / "oss")
    monkeypatch.setattr(oss.guard, "fetch_public", lambda url, **kw: FakeResponse())
    monkeypatch.setattr(oss.memory, "remember", lambda *a, **k: None)

    out = oss.fetch("acme/widget")
    assert out["ok"] is True
    assert out["files"] == 1
    got = oss.read("acme/widget", "main.py")
    assert got["ok"] and "print('hi')" in got["text"]


def test_fetch_uses_cache(tmp_path, monkeypatch):
    _make_repo(tmp_path, monkeypatch, {"main.py": "x\n"})

    def boom(*a, **k):
        raise AssertionError("should not re-download when cached")

    monkeypatch.setattr(oss.guard, "fetch_public", boom)
    out = oss.fetch("acme/widget")
    assert out["cached"] is True


def test_fetch_rejects_oversized(tmp_path, monkeypatch):
    class FakeResponse:
        status_code = 200
        content = b"x" * (oss.MAX_TARBALL_BYTES + 1)

    monkeypatch.setattr(oss, "OSS_ROOT", tmp_path / "oss")
    monkeypatch.setattr(oss.guard, "fetch_public", lambda url, **kw: FakeResponse())
    out = oss.fetch("acme/huge")
    assert "error" in out and "cap" in out["error"]


def test_install_requires_confirm(monkeypatch):
    monkeypatch.setattr(
        oss.memory, "create_pending", lambda kind, payload, ttl_sec=300: {"confirm_token": "tok", "kind": kind}
    )
    out = oss.install(package="requests")
    assert out["blocked"] is True
    assert out["confirm_token"] == "tok"


def test_install_rejects_bad_token(monkeypatch):
    monkeypatch.setattr(oss.memory, "consume_pending", lambda tok: None)
    out = oss.install(package="requests", confirm_token="wrong")
    assert "error" in out
    assert "Nothing installed" in out["error"]


def test_install_runs_after_confirm(monkeypatch):
    calls = []

    class Proc:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(
        oss.memory,
        "consume_pending",
        lambda tok: {"kind": "oss_install", "payload": {"repo": "", "package": "requests"}},
    )
    monkeypatch.setattr(oss.subprocess, "run", lambda *a, **k: (calls.append(a), Proc())[1])
    out = oss.install(package="requests", confirm_token="tok")
    assert out["ok"] is True
    assert "requests" in calls[0][0]


def test_install_needs_a_target():
    assert "error" in oss.install()


def test_fetch_builds_the_right_codeload_url(tmp_path, monkeypatch):
    """The one thing only a live call would otherwise catch. Egress is blocked in CI,
    so pin the URL shape instead of pretending the network was exercised."""
    seen = {}

    class FakeResponse:
        status_code = 404
        content = b""

    def fake_fetch(url, **kw):
        seen["url"] = url
        return FakeResponse()

    monkeypatch.setattr(oss, "OSS_ROOT", tmp_path / "oss")
    monkeypatch.setattr(oss.guard, "fetch_public", fake_fetch)

    oss.fetch("pola-rs/polars")
    assert seen["url"] == "https://codeload.github.com/pola-rs/polars/tar.gz/HEAD"

    oss.fetch("pola-rs/polars", "v1.2.3")
    assert seen["url"] == "https://codeload.github.com/pola-rs/polars/tar.gz/v1.2.3"


def test_fetch_reports_http_failure_cleanly(tmp_path, monkeypatch):
    class FakeResponse:
        status_code = 403
        content = b""

    monkeypatch.setattr(oss, "OSS_ROOT", tmp_path / "oss")
    monkeypatch.setattr(oss.guard, "fetch_public", lambda url, **kw: FakeResponse())
    out = oss.fetch("some/repo")
    assert "error" in out
    assert "403" in out["error"]


def test_fetch_reports_transport_failure_cleanly(tmp_path, monkeypatch):
    def boom(url, **kw):
        raise ValueError("Blocked private/loopback URL")

    monkeypatch.setattr(oss, "OSS_ROOT", tmp_path / "oss")
    monkeypatch.setattr(oss.guard, "fetch_public", boom)
    out = oss.fetch("some/repo")
    assert "error" in out and "Blocked" in out["error"]
