# Vendored MarketBeast (from D:\MARKETBEAST)

Two programs copied 2026-08-18:

| Folder | What |
|---|---|
| `hypertrader/` | Newer engine (v9). Conviction scoring, 0.45 threshold, `--debug`. **This is what Jarvis runs.** |
| `marketbeast hypertrader 8 - Copy/` | Earlier scanner (v8). Same menus, older score math. Kept as reference. |

API keys were stripped from both `scanner.py` files. IBKR still goes through official TWS on loopback (`app/ibkr.py`).
