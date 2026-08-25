"""Desktop / room-assistant moves borrowed from top GitHub Jarvis projects."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import webbrowser
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote_plus, urlparse

from . import catalog, config, obsidian, skills, widgets

ALLOWED_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "explorer": "explorer.exe",
    "edge": "msedge",
    "chrome": "chrome",
    "firefox": "firefox",
    "code": "code",
    "obsidian": "obsidian",
    "spotify": "spotify",
    "word": "winword",
    "excel": "excel",
    "powershell": "powershell",
}

JOKES = (
    "I would tell you a UDP joke, but you might not get it.",
    "There are only 10 kinds of people: those who understand binary and those who do not.",
    "I ran a diagnostic on humor. The result was: dry, British, and slightly unhelpful. Perfect.",
    "Your RAM is fine. It is the humans who keep leaking state.",
    "I considered a knock-knock joke, but I already know who is there.",
    "A SQL query walks into a bar, walks up to two tables, and asks: may I join you?",
)


def _safe(text: str, n: int = 80) -> str:
    return re.sub(r"[^A-Za-z0-9 .,:!?@#\-/]", "", text or "")[:n]


def situation() -> str:
    now = widgets.now()
    return (
        f"# SITUATION\n"
        f"- Local: {now.get('local')} ({now.get('tz')}, {now.get('local_weekday')})\n"
        f"- UTC: {now.get('utc')} ({now.get('weekday')})\n"
        f"- Host: {platform.node()} {platform.system()} {platform.release()}\n"
        f"- Default locale: Houston unless the owner says otherwise\n"
        f"- Wake word: Jarvis (HUD can listen continuously)\n"
        f"- Greeting: {skills.greeting()}\n"
    )


def open_url(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"error": "Only http(s) URLs"}
    webbrowser.open(url)
    return {"ok": True, "opened": url}


def youtube(query: str) -> dict:
    url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
    return open_url(url)


def maps(query: str) -> dict:
    url = "https://www.google.com/maps/search/" + quote_plus(query)
    geo = catalog.call("geocode", query)
    opened = open_url(url)
    return {"opened": opened, "geocode": geo}


def google(query: str) -> dict:
    return open_url("https://www.google.com/search?q=" + quote_plus(query or ""))


def open_app(name: str) -> dict:
    key = (name or "").strip().lower()
    exe = ALLOWED_APPS.get(key)
    if not exe:
        return {"error": f"App not in whitelist: {name}", "allowed": sorted(set(ALLOWED_APPS))}
    resolved = shutil.which(exe)
    if not resolved:
        return {"error": f"{exe} not on PATH", "app": key}
    subprocess.Popen([resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "app": key, "exe": resolved}


# --------------------------------------------------------------------------- pywinauto
#
# open_app() launches an executable and hopes. It cannot tell whether the window
# appeared, cannot bring an already-running app forward, and cannot touch anything
# inside it. pywinauto talks to the Windows UI Automation tree, so these do.
#
# Everything here degrades: no pywinauto, or not Windows, and each returns a clear
# error rather than raising. The launch-and-hope path stays exactly as it was.


def ui_available() -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import pywinauto  # noqa: F401

        return True
    except ImportError:
        return False


def _ui_unavailable() -> dict:
    if platform.system() != "Windows":
        return {"error": f"UI automation is Windows-only; this is {platform.system()}."}
    return {"error": "pywinauto not installed.", "fix": "pip install pywinauto"}


def list_windows(limit: int = 30) -> dict:
    """Every top-level window with a title, so the caller can name one."""
    if not ui_available():
        return _ui_unavailable()
    try:
        from pywinauto import Desktop

        rows = []
        for w in Desktop(backend="uia").windows():
            try:
                title = w.window_text()
            except Exception:
                continue
            if title and title.strip():
                rows.append({"title": _safe(title, 120), "class": w.class_name()})
            if len(rows) >= limit:
                break
        return {"ok": True, "count": len(rows), "windows": rows}
    except Exception as exc:
        return {"error": str(exc)[:300]}


def focus_window(title: str) -> dict:
    """Bring a window forward by (partial) title. open_app cannot do this."""
    title = (title or "").strip()
    if not title:
        return {"error": "title required."}
    if not ui_available():
        return _ui_unavailable()
    try:
        from pywinauto import Desktop

        win = Desktop(backend="uia").window(title_re=f".*{re.escape(title)}.*")
        win.wait("exists", timeout=5)
        win.set_focus()
        return {"ok": True, "focused": _safe(win.window_text(), 120)}
    except Exception as exc:
        return {"error": f"no window matching {title!r}: {str(exc)[:200]}"}


def send_keys(keys: str, *, window: str = "") -> dict:
    """Type into the focused window, or into one named by title.

    Deliberately NOT a general keyboard driver: the text is capped, and a window has
    to be focusable first, so this cannot quietly type into whatever happens to be in
    front of it.
    """
    keys = (keys or "").strip()
    if not keys:
        return {"error": "keys required."}
    if len(keys) > 500:
        return {"error": f"refusing to send {len(keys)} characters; cap is 500."}
    if not ui_available():
        return _ui_unavailable()

    if window:
        focused = focus_window(window)
        if not focused.get("ok"):
            return focused
    try:
        from pywinauto.keyboard import send_keys as _send

        _send(keys, with_spaces=True)
        return {"ok": True, "sent": len(keys), "window": window or "focused"}
    except Exception as exc:
        return {"error": str(exc)[:300]}


def window_text(title: str, limit: int = 4000) -> dict:
    """Read the visible text out of a window — see what an app is showing."""
    title = (title or "").strip()
    if not title:
        return {"error": "title required."}
    if not ui_available():
        return _ui_unavailable()
    try:
        from pywinauto import Desktop

        win = Desktop(backend="uia").window(title_re=f".*{re.escape(title)}.*")
        win.wait("exists", timeout=5)
        chunks = []
        for ctrl in win.descendants():
            try:
                t = ctrl.window_text()
            except Exception:
                continue
            if t and t.strip():
                chunks.append(t.strip())
            if sum(len(c) for c in chunks) > limit:
                break
        return {"ok": True, "window": _safe(win.window_text(), 120), "text": "\n".join(chunks)[:limit]}
    except Exception as exc:
        return {"error": str(exc)[:300]}


def ui_status() -> dict:
    return {
        "ok": True,
        "platform": platform.system(),
        "pywinauto": ui_available(),
        "actions": ["windows", "focus", "type", "read"] if ui_available() else [],
        "note": (
            "Real UI automation via pywinauto."
            if ui_available()
            else _ui_unavailable().get("error")
        ),
    }


def notify(title: str, body: str = "") -> dict:
    title = _safe(title or "Jarvis", 80)
    body = _safe(body or "", 200)
    if platform.system() == "Windows":
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
            "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            f'$t.GetElementsByTagName("text").Item(0).AppendChild($t.CreateTextNode("{title}")) | Out-Null; '
            f'$t.GetElementsByTagName("text").Item(1).AppendChild($t.CreateTextNode("{body}")) | Out-Null; '
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($t); "
            '[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Super Jarvis").Show($toast)'
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                timeout=8,
                capture_output=True,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    return {"ok": True, "title": title, "body": body}


def sysinfo() -> dict:
    info: dict[str, Any] = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cwd": os.getcwd(),
        "host": platform.node(),
    }
    try:
        du = shutil.disk_usage(os.path.abspath(os.sep))
        info["disk_free_gb"] = round(du.free / 1024**3, 1)
        info["disk_total_gb"] = round(du.total / 1024**3, 1)
    except Exception:
        pass
    try:
        import psutil  # type: ignore

        info["cpu_percent"] = psutil.cpu_percent(interval=0.15)
        info["ram_percent"] = psutil.virtual_memory().percent
        batt = psutil.sensors_battery()
        if batt:
            info["battery_percent"] = batt.percent
            info["power_plugged"] = batt.power_plugged
    except Exception:
        if platform.system() == "Windows":
            try:
                raw = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory;"
                     "(Get-CimInstance Win32_Processor).LoadPercentage"],
                    timeout=8,
                    capture_output=True,
                    text=True,
                )
                nums = [n.strip() for n in (raw.stdout or "").splitlines() if n.strip().isdigit()]
                if nums:
                    info["free_ram_kb"] = int(nums[0])
                if len(nums) > 1:
                    info["cpu_load"] = int(nums[1])
            except Exception:
                pass
    return info


def email_draft(to: str, subject: str, body: str) -> dict:
    note = f"---\ntype: email\nto: {to}\nsubject: {subject}\n---\n\n# {subject}\n\nTo: {to}\n\n{body}\n"
    slug = _safe(subject or "email", 40).replace(" ", "-") or "email"
    path = f"Inbox/email-{slug}.md"
    obsidian.write_note(path, note)
    return {"ok": True, "path": path, "note": "Draft only. Use email_send after Microsoft login."}


def email_send(to: str, subject: str, body: str) -> dict:
    from . import msgraph

    sent = msgraph.send_mail(to, subject, body)
    if sent.get("ok"):
        email_draft(to, subject, body + "\n\n_sent via Microsoft Graph_")
    return sent


def screenshot(name: str = "") -> dict:
    dest_dir = config.WORKSPACE_DIR / "images"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = _safe(name or "shot", 32).replace(" ", "-") or "shot"
    dest = dest_dir / f"{slug}-{stamp}.png"
    if platform.system() != "Windows":
        return {"error": "Screenshot is Windows-only for now", "path": str(dest)}
    ps_path = str(dest).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$b = [System.Windows.Forms.SystemInformation]::VirtualScreen; "
        "$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; "
        "$g = [System.Drawing.Graphics]::FromImage($bmp); "
        "$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size); "
        f"$bmp.Save('{ps_path}'); "
        "$g.Dispose(); $bmp.Dispose()"
    )
    try:
        run = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            timeout=12,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if not dest.exists():
        return {"ok": False, "error": (run.stderr or "screenshot failed")[:300]}
    note = f"# Screenshot {stamp}\n\nSaved to `{dest}`.\n"
    obsidian.write_note(f"Inbox/screenshot-{stamp}.md", note)
    return {"ok": True, "path": str(dest), "bytes": dest.stat().st_size}


def clipboard(action: str = "get", text: str = "") -> dict:
    if platform.system() != "Windows":
        return {"error": "Clipboard helpers are Windows-only for now"}
    if action == "set":
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
                input=text or "",
                timeout=8,
                capture_output=True,
                text=True,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "action": "set", "chars": len(text or "")}
    try:
        run = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
            timeout=8,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    clip = (run.stdout or "")[:4000]
    return {"ok": True, "action": "get", "text": clip}


def joke() -> dict:
    idx = int(datetime.now().timestamp()) % len(JOKES)
    return {"joke": JOKES[idx]}


def note(text: str) -> dict:
    from .redact import redact

    body = redact((text or "").strip())
    if not body:
        return {"error": "empty note"}
    captured = obsidian.capture_memory("note", body, tags=["desktop", "voice"])
    return {"ok": True, "saved": captured}


def remind(title: str, when: str = "", minutes: int = 0) -> dict:
    from . import opensource, reminders

    stamp = when.strip()
    if minutes:
        stamp = (datetime.now(timezone.utc) + timedelta(minutes=int(minutes))).isoformat()
    if not stamp:
        stamp = datetime.now(timezone.utc).replace(hour=17, minute=0, second=0, microsecond=0).isoformat()
        if datetime.now(timezone.utc).hour >= 17:
            stamp = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            ).isoformat()
    live = reminders.add(title or "Reminder", stamp, minutes=0, kind="reminder")
    item = opensource.calendar_add(title or "Reminder", stamp, "Jarvis reminder")
    try:
        notify("Reminder set", title or "Reminder")
    except Exception:
        pass
    return {"ok": True, "when": stamp, "event": item, "reminder": live}


def timer(minutes: int = 5, title: str = "") -> dict:
    from . import reminders

    mins = max(1, int(minutes or 5))
    item = reminders.timer(mins, title or f"{mins} minute timer")
    try:
        notify("Timer set", item["title"])
    except Exception:
        pass
    return {"ok": True, "minutes": mins, "reminder": item}


def find(query: str) -> dict:
    from . import workspace

    vault = {}
    try:
        vault = obsidian.search(query)
    except Exception as exc:
        vault = {"error": str(exc)}
    files = {}
    try:
        files = workspace.find(query)
    except Exception as exc:
        files = {"error": str(exc)}
    return {"query": query, "vault": vault, "workspace": files}


def plan_day() -> dict:
    from . import opensource

    tasks = []
    try:
        tasks = obsidian.list_tasks(open_only=True)[:8]
    except Exception:
        pass
    cal = {}
    try:
        cal = opensource.calendar_list(8)
    except Exception:
        pass
    weather = {}
    try:
        weather = widgets.weather()
    except Exception as exc:
        weather = {"error": str(exc)}
    coming = []
    try:
        from . import reminders

        coming = reminders.list_items(open_only=True, limit=6)
    except Exception:
        pass
    cal = cal if isinstance(cal, dict) else {}
    try:
        from . import msgraph

        if msgraph.ready():
            cal = {**cal, "microsoft": msgraph.calendar_today()}
    except Exception:
        pass
    return {
        "greeting": skills.greeting(),
        "now": widgets.now(),
        "weather": weather,
        "tasks": tasks,
        "calendar": cal,
        "reminders": coming,
    }


def capabilities() -> dict:
    return {"skills": skills.catalog(), "apps": sorted(set(ALLOWED_APPS))}


CLAUDE_APP_INSTALL = "https://github.com/apps/claude/installations/new"


def claude_github_app() -> dict:
    """Open Anthropic's Claude GitHub App install page. Does not replace Grok."""
    opened = open_url(CLAUDE_APP_INSTALL)
    return {
        "ok": True,
        "opened": opened,
        "app": "https://github.com/apps/claude",
        "repo": "rkenagy-ops/jarvis-system",
        "next": [
            "Install the app on jarvis-system only.",
            "Add Actions secret ANTHROPIC_API_KEY.",
            "Comment @claude on an issue or PR. HUD stays Grok.",
        ],
        "workflow": ".github/workflows/claude.yml",
    }


def dispatch(action: str, **kwargs) -> Any:
    if action in {"claude_app", "claude_github", "install_claude"}:
        return claude_github_app()
    # --- real UI control, beyond launch-and-hope
    if action in {"ui", "ui_status"}:
        return ui_status()
    if action in {"windows", "list_windows"}:
        return list_windows(int(kwargs.get("limit") or 30))
    if action in {"focus", "focus_window"}:
        return focus_window(str(kwargs.get("title") or kwargs.get("window") or ""))
    if action in {"type", "send_keys"}:
        return send_keys(
            str(kwargs.get("keys") or kwargs.get("text") or ""),
            window=str(kwargs.get("window") or kwargs.get("title") or ""),
        )
    if action in {"read", "window_text"}:
        return window_text(str(kwargs.get("title") or kwargs.get("window") or ""))
    # --- persistent native window
    if action in {"hud", "hud_status"}:
        from . import hud

        return hud.status()
    if action in {"hud_launch", "window"}:
        from . import hud

        return hud.launch_detached(str(kwargs.get("url") or ""))
    if action in {"comment", "hamburger", "switch_account", "engage", "feed"}:
        from . import stack

        return {
            **stack.refuse_browser_farm(),
            "hint": "To automate your own first comment: stack action=comment account_id=... text=... comment=...",
        }
    if action == "open":
        url = kwargs.get("url") or ""
        if url:
            return open_url(url)
        return open_app(kwargs.get("app") or kwargs.get("query") or "")
    if action == "app":
        return open_app(kwargs.get("app") or kwargs.get("query") or "")
    if action == "youtube":
        return youtube(kwargs.get("query") or "")
    if action == "maps":
        return maps(kwargs.get("query") or "")
    if action == "google":
        return google(kwargs.get("query") or "")
    if action == "notify":
        return notify(kwargs.get("title") or "Jarvis", kwargs.get("body") or "")
    if action == "sysinfo":
        return sysinfo()
    if action == "email_draft":
        return email_draft(kwargs.get("to") or "", kwargs.get("subject") or "Note", kwargs.get("body") or "")
    if action == "email_send":
        return email_send(kwargs.get("to") or "", kwargs.get("subject") or "Note", kwargs.get("body") or "")
    if action == "screenshot":
        return screenshot(kwargs.get("name") or kwargs.get("query") or "")
    if action == "clipboard":
        return clipboard(kwargs.get("mode") or "get", kwargs.get("body") or kwargs.get("text") or "")
    if action == "joke":
        return joke()
    if action == "note":
        return note(kwargs.get("body") or kwargs.get("query") or "")
    if action == "remind":
        return remind(
            kwargs.get("title") or kwargs.get("query") or "Reminder",
            kwargs.get("when") or "",
            int(kwargs.get("minutes") or 0),
        )
    if action == "timer":
        return timer(int(kwargs.get("minutes") or 5), kwargs.get("title") or kwargs.get("query") or "")
    if action == "find":
        return find(kwargs.get("query") or "")
    if action in {"plan", "plan_day"}:
        return plan_day()
    if action in {"calendar_sync", "sync_calendar"}:
        from . import msgraph

        return msgraph.sync_calendar()
    if action in {"skills", "capabilities"}:
        return capabilities()
    if action == "situation":
        return {"text": situation()}
    if action in {"vault", "open_vault"}:
        from . import daily as daily_mod

        return daily_mod.open_vault()
    if action == "daily":
        from . import daily as daily_mod

        return daily_mod.pack()
    return {"error": f"Unknown desktop action {action}"}
