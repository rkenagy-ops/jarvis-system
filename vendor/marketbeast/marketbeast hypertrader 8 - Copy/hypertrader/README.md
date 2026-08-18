# HyperTrader - AI Options Scanner & Trading System

Scans DOW 30, NASDAQ 100, S&P 500, Russell 2000, and 60+ ETFs to find the best options opportunities.

## Quick Start

### 1. Install Python
Download from https://python.org/downloads
**Check "Add Python to PATH" during installation!**

### 2. Install Dependencies
```cmd
pip install pandas numpy yfinance ib_insync
```

### 3. Run the Scanner
Double-click `HyperTrader.bat` or run:
```cmd
python scanner.py --best --top 10
```

## Usage

### Find Best Options (Recommended)
```cmd
python scanner.py --best              # Top 20 options across all markets
python scanner.py --best --top 10     # Top 10
python scanner.py --best --bullish    # Bullish only
python scanner.py --best --bearish    # Bearish only
```

### Scan Specific Indices
```cmd
python scanner.py --sector dow        # DOW 30
python scanner.py --sector nasdaq     # NASDAQ 100
python scanner.py --sector sp500      # S&P 500
python scanner.py --sector russell    # Russell 2000
python scanner.py --sector etfs       # All ETFs
```

### Deep Analysis
```cmd
python scanner.py -s NVDA --deep      # Single stock with options
python scanner.py -s NVDA --deep --dte 14  # 2-week options
```

### Export Results
```cmd
python scanner.py --best --export results.csv
```

## For IBKR Trading

1. Install TWS or IB Gateway
2. Enable API in TWS settings (port 7497 for paper)
3. Run `python diagnose_ibkr.py` to test connection

## Files

| File | Description |
|------|-------------|
| `HyperTrader.bat` | Main menu (Windows) |
| `find_best_options.bat` | Quick best options scan |
| `scanner.py` | Standalone scanner |
| `diagnose_ibkr.py` | IBKR connection tester |

## Coverage

- **DOW 30**: 30 blue-chip stocks
- **NASDAQ 100**: 100 tech-heavy stocks  
- **S&P 500**: Top 100 stocks
- **Russell 2000**: 40 high-volatility small caps
- **ETFs**: 60+ sector, leveraged, and thematic ETFs
- **Total**: 250+ unique symbols

## Disclaimer

This is for educational purposes only. Trading options involves substantial risk.
Not financial advice. Use at your own risk.
