---
type: skill
name: native-hud-device
---

# Persistent HUD + real device control

The last two capability gaps. Both need a library `start.bat` now installs for you.

## Native HUD window

```
desktop action=hud          # can it? which backend?
desktop action=hud_launch   # open the window
python -m app.hud           # or from a terminal, against a running Jarvis
```

Wraps the **same** FastAPI page in an OS window with its own taskbar entry — no second
UI to maintain. Opens as a **detached subprocess**: pywebview needs the main thread and
uvicorn already owns it, so launching in-process would deadlock one of them.

The window carries the guard token in the URL, so it isn't bounced by the fortress check.

## Windows UI control

`open_app()` launches an executable and hopes. It can't tell whether the window appeared,
can't bring a running app forward, and can't touch anything inside it. These can:

```
desktop action=ui                              # is pywinauto available?
desktop action=windows                         # every titled top-level window
desktop action=focus title=Notepad             # bring one forward
desktop action=type window=Notepad keys="hi"   # type into a named window
desktop action=read title=Notepad              # pull visible text out of one
```

`type` is deliberately **not** a general keyboard driver: text is capped at 500 chars, and
the window must focus first — so it can't quietly type into whatever happens to be in
front. If focus fails, nothing is sent.

Everything degrades: no pywinauto, or not Windows, and each returns a clear error naming
the fix. The old launch-and-hope path is unchanged.

## What is not verified

The window has never been opened and pywinauto has never driven a real window — neither
is possible from a headless Linux container. Backend selection, URL and token handling,
subprocess launch, argument validation and every failure path are tested. **The pixels
and the UI tree are not.** First run is yours.
