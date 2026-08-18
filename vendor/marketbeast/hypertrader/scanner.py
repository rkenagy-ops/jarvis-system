#!/usr/bin/env python3
"""
HyperTrader Standalone Scanner
==============================
Scans DOW, NASDAQ, S&P 500, Russell 2000 & ETFs for best options opportunities.
Works without IBKR - just generates signals for manual execution.

Usage:
    python scanner.py                      # Default scan
    python scanner.py --best               # Find BEST options across all markets
    python scanner.py --best --top 10      # Top 10 best options
    python scanner.py -s AAPL,NVDA --deep  # Deep analysis with options
    python scanner.py --sector nasdaq      # Scan NASDAQ 100
"""

import argparse
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np

try:
    import yfinance as yf
except ImportError:
    print("Please install yfinance: pip install yfinance")
    sys.exit(1)


# ==================== Configuration ====================

# API Keys
ALPHA_VANTAGE_KEY = ""
FINNHUB_KEY = ""

# Major Index Components
DOW_30 = [
    'AAPL', 'AMGN', 'AXP', 'BA', 'CAT', 'CRM', 'CSCO', 'CVX', 'DIS', 'DOW',
    'GS', 'HD', 'HON', 'IBM', 'INTC', 'JNJ', 'JPM', 'KO', 'MCD', 'MMM',
    'MRK', 'MSFT', 'NKE', 'PG', 'TRV', 'UNH', 'V', 'VZ', 'WBA', 'WMT'
]

NASDAQ_100 = [
    'AAPL', 'ABNB', 'ADBE', 'ADI', 'ADP', 'ADSK', 'AEP', 'AMAT', 'AMD', 'AMGN',
    'AMZN', 'ANSS', 'ARM', 'ASML', 'AVGO', 'AZN', 'BIIB', 'BKNG', 'BKR', 'CDNS',
    'CDW', 'CEG', 'CHTR', 'CMCSA', 'COST', 'CPRT', 'CRWD', 'CSCO', 'CSGP', 'CSX',
    'CTAS', 'CTSH', 'DDOG', 'DLTR', 'DXCM', 'EA', 'EXC', 'FANG', 'FAST', 'FTNT',
    'GEHC', 'GFS', 'GILD', 'GOOG', 'GOOGL', 'HON', 'IDXX', 'ILMN', 'INTC', 'INTU',
    'ISRG', 'KDP', 'KHC', 'KLAC', 'LIN', 'LRCX', 'LULU', 'MAR', 'MCHP', 'MDB',
    'MDLZ', 'MELI', 'META', 'MNST', 'MRNA', 'MRVL', 'MSFT', 'MU', 'NFLX', 'NVDA',
    'NXPI', 'ODFL', 'ON', 'ORLY', 'PANW', 'PAYX', 'PCAR', 'PDD', 'PEP', 'PYPL',
    'QCOM', 'REGN', 'ROP', 'ROST', 'SBUX', 'SMCI', 'SNPS', 'TEAM', 'TMUS', 'TSLA',
    'TTD', 'TTWO', 'TXN', 'VRSK', 'VRTX', 'WBD', 'WDAY', 'XEL', 'ZS'
]

SP500_TOP_100 = [
    'AAPL', 'ABBV', 'ABT', 'ACN', 'ADBE', 'AIG', 'AMD', 'AMGN', 'AMT', 'AMZN',
    'AVGO', 'AXP', 'BA', 'BAC', 'BK', 'BKNG', 'BLK', 'BMY', 'C', 'CAT',
    'CHTR', 'CL', 'CMCSA', 'COF', 'COP', 'COST', 'CRM', 'CSCO', 'CVS', 'CVX',
    'DE', 'DHR', 'DIS', 'DUK', 'EMR', 'EXC', 'F', 'FDX', 'GD', 'GE',
    'GILD', 'GM', 'GOOG', 'GOOGL', 'GS', 'HD', 'HON', 'IBM', 'INTC', 'INTU',
    'ISRG', 'JNJ', 'JPM', 'KO', 'LIN', 'LLY', 'LMT', 'LOW', 'MA', 'MCD',
    'MDLZ', 'MDT', 'MET', 'META', 'MMM', 'MO', 'MRK', 'MS', 'MSFT', 'NEE',
    'NFLX', 'NKE', 'NOW', 'NVDA', 'ORCL', 'PEP', 'PFE', 'PG', 'PM', 'PYPL',
    'QCOM', 'RTX', 'SBUX', 'SCHW', 'SO', 'SPG', 'T', 'TGT', 'TMO', 'TMUS',
    'TSLA', 'TXN', 'UNH', 'UNP', 'UPS', 'USB', 'V', 'VZ', 'WFC', 'WMT', 'XOM'
]

RUSSELL_2000_TOP = [
    'SMCI', 'RIOT', 'MARA', 'PLUG', 'SOUN', 'IONQ', 'AFRM', 'UPST', 'SOFI', 'HOOD',
    'RKLB', 'JOBY', 'LAZR', 'LCID', 'RIVN', 'DNA', 'PATH', 'U', 'DOCS', 'CELH',
    'AXON', 'DECK', 'TOST', 'DUOL', 'CRSP', 'NTLA', 'BEAM', 'EXAS', 'HUBS', 'PCTY',
    'PAYC', 'WIX', 'ETSY', 'ROKU', 'Z', 'PINS', 'SNAP', 'LYFT', 'DASH', 'ABNB'
]

# Comprehensive ETF List
ETFS = {
    'broad_market': ['SPY', 'QQQ', 'IWM', 'DIA', 'VOO', 'VTI', 'RSP'],
    'sector': ['XLF', 'XLE', 'XLK', 'XLV', 'XLI', 'XLC', 'XLY', 'XLP', 'XLU', 'XLB', 'XLRE'],
    'growth_value': ['VUG', 'VTV', 'IWF', 'IWD', 'MGK', 'SCHG'],
    'tech_semi': ['SMH', 'SOXX', 'IGV', 'ARKK', 'ARKW', 'XBI', 'IBB'],
    'energy': ['XOP', 'OIH', 'USO', 'UNG', 'ICLN', 'TAN'],
    'financials': ['KRE', 'KBE', 'IAI'],
    'metals': ['GLD', 'SLV', 'GDX', 'GDXJ', 'COPX'],
    'bonds': ['TLT', 'HYG', 'LQD', 'JNK', 'BND'],
    'leveraged': ['TQQQ', 'SQQQ', 'SPXL', 'SPXS', 'SOXL', 'SOXS'],
    'international': ['EEM', 'EFA', 'FXI', 'EWZ', 'EWJ'],
    'crypto_related': ['BITO', 'MSTR', 'COIN', 'MARA', 'RIOT'],
}

ALL_ETFS = list(set([etf for etfs in ETFS.values() for etf in etfs]))

# Watchlist by category
WATCHLIST = {
    'dow': DOW_30,
    'nasdaq': list(set(NASDAQ_100)),
    'sp500': list(set(SP500_TOP_100)),
    'russell': RUSSELL_2000_TOP,
    'etfs': ALL_ETFS,
    'tech': ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'META', 'AMD', 'TSLA', 'AMZN', 'CRM', 'AVGO', 'ORCL', 'INTC'],
    'healthcare': ['JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT', 'BMY', 'GILD'],
    'financials': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'C', 'AXP', 'SCHW', 'COF'],
    'consumer': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'TGT', 'COST', 'WMT', 'LOW'],
    'energy': ['XOM', 'CVX', 'COP', 'SLB', 'OXY', 'EOG', 'MPC', 'VLO', 'PSX', 'HAL'],
    'industrials': ['CAT', 'BA', 'GE', 'HON', 'UNP', 'LMT', 'RTX', 'DE', 'UPS', 'FDX'],
    'all': [],
}

# Full market scan (all unique symbols)
FULL_MARKET = list(set(DOW_30 + NASDAQ_100 + SP500_TOP_100 + RUSSELL_2000_TOP + ALL_ETFS))
WATCHLIST['all'] = FULL_MARKET
ALL_SYMBOLS = FULL_MARKET

SYMBOL_COUNTS = {
    'DOW': len(DOW_30),
    'NASDAQ': len(set(NASDAQ_100)),
    'SP500': len(set(SP500_TOP_100)),
    'RUSSELL': len(RUSSELL_2000_TOP),
    'ETFs': len(ALL_ETFS),
    'TOTAL': len(FULL_MARKET),
}


# ==================== Colors ====================

class C:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'
    
    @classmethod
    def disable(cls):
        cls.GREEN = cls.RED = cls.YELLOW = cls.BLUE = ''
        cls.MAGENTA = cls.CYAN = cls.BOLD = cls.END = ''


# Disable colors on Windows if not supported
if sys.platform == 'win32':
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except:
        C.disable()


# ==================== Technical Indicators ====================

def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = calculate_ema(series, 12)
    ema26 = calculate_ema(series, 26)
    macd = ema12 - ema26
    signal = calculate_ema(macd, 9)
    histogram = macd - signal
    return macd, signal, histogram

def calculate_bollinger_bands(series: pd.Series, period: int = 20, std: float = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
    sma = calculate_sma(series, period)
    std_dev = series.rolling(window=period).std()
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    return upper, sma, lower

def calculate_stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    d = k.rolling(window=d_period).mean()
    return k, d

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def calculate_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    return obv

def calculate_vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    typical_price = (high + low + close) / 3
    return (typical_price * volume).cumsum() / volume.cumsum()


# ==================== Scanner Class ====================

class StockScanner:
    """Standalone stock and options scanner"""
    
    def __init__(self):
        self.cache = {}
    
    def fetch_data(self, symbol: str, period: str = '3mo') -> Optional[pd.DataFrame]:
        """Fetch OHLCV data from Yahoo Finance"""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)
            if df is None or df.empty:
                return None
            if len(df) < 5:
                return None
            return df
        except Exception as e:
            # Silently fail - common for some symbols
            return None
    
    def analyze(self, symbol: str, df: pd.DataFrame) -> Dict:
        """Analyze a stock and generate signals"""
        
        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']
        
        current_price = close.iloc[-1]
        
        # Calculate indicators
        rsi = calculate_rsi(close)
        macd, macd_signal, macd_hist = calculate_macd(close)
        bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(close)
        stoch_k, stoch_d = calculate_stochastic(high, low, close)
        atr = calculate_atr(high, low, close)
        
        sma_20 = calculate_sma(close, 20)
        sma_50 = calculate_sma(close, 50)
        sma_200 = calculate_sma(close, 200)
        ema_9 = calculate_ema(close, 9)
        ema_21 = calculate_ema(close, 21)
        
        # Volume analysis
        vol_sma = calculate_sma(volume, 20)
        volume_ratio = volume.iloc[-1] / vol_sma.iloc[-1] if vol_sma.iloc[-1] > 0 else 1
        
        # Price changes
        change_1d = (close.iloc[-1] / close.iloc[-2] - 1) if len(close) > 1 else 0
        change_1w = (close.iloc[-1] / close.iloc[-5] - 1) if len(close) > 5 else 0
        change_1m = (close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 21 else 0
        
        # Generate signals
        signals = []
        bullish_score = 0
        bearish_score = 0
        
        # RSI signals
        rsi_val = rsi.iloc[-1]
        if rsi_val < 30:
            signals.append(('RSI Oversold', 'bullish', 0.8))
            bullish_score += 15
        elif rsi_val < 40:
            signals.append(('RSI Low', 'bullish', 0.5))
            bullish_score += 8
        elif rsi_val > 70:
            signals.append(('RSI Overbought', 'bearish', 0.8))
            bearish_score += 15
        elif rsi_val > 60:
            signals.append(('RSI High', 'bearish', 0.5))
            bearish_score += 8
        
        # MACD signals
        if macd.iloc[-1] > macd_signal.iloc[-1] and macd.iloc[-2] <= macd_signal.iloc[-2]:
            signals.append(('MACD Bullish Cross', 'bullish', 0.9))
            bullish_score += 20
        elif macd.iloc[-1] < macd_signal.iloc[-1] and macd.iloc[-2] >= macd_signal.iloc[-2]:
            signals.append(('MACD Bearish Cross', 'bearish', 0.9))
            bearish_score += 20
        
        if macd_hist.iloc[-1] > 0 and macd_hist.iloc[-1] > macd_hist.iloc[-2]:
            signals.append(('MACD Histogram Rising', 'bullish', 0.6))
            bullish_score += 10
        elif macd_hist.iloc[-1] < 0 and macd_hist.iloc[-1] < macd_hist.iloc[-2]:
            signals.append(('MACD Histogram Falling', 'bearish', 0.6))
            bearish_score += 10
        
        # Bollinger Band signals
        if current_price < bb_lower.iloc[-1]:
            signals.append(('Below Lower BB', 'bullish', 0.7))
            bullish_score += 12
        elif current_price > bb_upper.iloc[-1]:
            signals.append(('Above Upper BB', 'bearish', 0.7))
            bearish_score += 12
        
        # Stochastic signals
        if stoch_k.iloc[-1] < 20 and stoch_d.iloc[-1] < 20:
            signals.append(('Stochastic Oversold', 'bullish', 0.7))
            bullish_score += 12
        elif stoch_k.iloc[-1] > 80 and stoch_d.iloc[-1] > 80:
            signals.append(('Stochastic Overbought', 'bearish', 0.7))
            bearish_score += 12
        
        # Trend signals (Moving Averages)
        if current_price > sma_20.iloc[-1] > sma_50.iloc[-1]:
            signals.append(('Uptrend (Price > SMA20 > SMA50)', 'bullish', 0.8))
            bullish_score += 15
        elif current_price < sma_20.iloc[-1] < sma_50.iloc[-1]:
            signals.append(('Downtrend (Price < SMA20 < SMA50)', 'bearish', 0.8))
            bearish_score += 15
        
        # Golden/Death Cross
        if sma_50.iloc[-1] > sma_200.iloc[-1] and sma_50.iloc[-2] <= sma_200.iloc[-2]:
            signals.append(('Golden Cross', 'bullish', 1.0))
            bullish_score += 25
        elif sma_50.iloc[-1] < sma_200.iloc[-1] and sma_50.iloc[-2] >= sma_200.iloc[-2]:
            signals.append(('Death Cross', 'bearish', 1.0))
            bearish_score += 25
        
        # EMA momentum
        if ema_9.iloc[-1] > ema_21.iloc[-1]:
            signals.append(('EMA 9 > EMA 21', 'bullish', 0.6))
            bullish_score += 8
        else:
            signals.append(('EMA 9 < EMA 21', 'bearish', 0.6))
            bearish_score += 8
        
        # Volume confirmation
        if volume_ratio > 1.5 and change_1d > 0:
            signals.append(('High Volume Up', 'bullish', 0.7))
            bullish_score += 10
        elif volume_ratio > 1.5 and change_1d < 0:
            signals.append(('High Volume Down', 'bearish', 0.7))
            bearish_score += 10
        
        # Calculate overall score (0-1 scale)
        # Normalize to 0-1 range based on signal strength
        max_possible = 100  # Approximate max score
        normalized_bullish = min(bullish_score / max_possible, 1.0)
        normalized_bearish = min(bearish_score / max_possible, 1.0)
        
        # Score represents conviction: higher = stronger signal either direction
        if bullish_score > bearish_score:
            score = 0.5 + (normalized_bullish - normalized_bearish) * 0.5
        elif bearish_score > bullish_score:
            score = 0.5 + (normalized_bearish - normalized_bullish) * 0.5
        else:
            score = 0.5
        
        # Ensure score is in valid range
        score = max(0.0, min(1.0, score))
        
        # Determine direction
        if bullish_score > bearish_score + 10:
            direction = 'BULLISH'
        elif bearish_score > bullish_score + 10:
            direction = 'BEARISH'
        else:
            direction = 'NEUTRAL'
        
        # Calculate stop loss and target based on ATR
        atr_val = atr.iloc[-1]
        if direction == 'BULLISH':
            stop_loss = current_price - (2 * atr_val)
            target = current_price + (3 * atr_val)
        elif direction == 'BEARISH':
            stop_loss = current_price + (2 * atr_val)
            target = current_price - (3 * atr_val)
        else:
            stop_loss = current_price - (1.5 * atr_val)
            target = current_price + (1.5 * atr_val)
        
        risk_reward = abs(target - current_price) / abs(current_price - stop_loss) if abs(current_price - stop_loss) > 0 else 0
        
        return {
            'symbol': symbol,
            'price': current_price,
            'change_1d': change_1d,
            'change_1w': change_1w,
            'change_1m': change_1m,
            'rsi': rsi_val,
            'macd': macd.iloc[-1],
            'macd_signal': macd_signal.iloc[-1],
            'macd_hist': macd_hist.iloc[-1],
            'stoch_k': stoch_k.iloc[-1],
            'stoch_d': stoch_d.iloc[-1],
            'bb_upper': bb_upper.iloc[-1],
            'bb_lower': bb_lower.iloc[-1],
            'sma_20': sma_20.iloc[-1],
            'sma_50': sma_50.iloc[-1],
            'sma_200': sma_200.iloc[-1] if len(close) >= 200 else None,
            'atr': atr_val,
            'atr_pct': atr_val / current_price * 100,
            'volume': volume.iloc[-1],
            'volume_ratio': volume_ratio,
            'score': score,
            'direction': direction,
            'bullish_score': bullish_score,
            'bearish_score': bearish_score,
            'signals': signals,
            'stop_loss': stop_loss,
            'target': target,
            'risk_reward': risk_reward,
        }
    
    def get_options_data(self, symbol: str, target_dte: int = 7) -> Optional[Dict]:
        """Get options chain data targeting specific DTE (default: 1 week)"""
        try:
            import math
            from datetime import datetime, timedelta
            
            ticker = yf.Ticker(symbol)
            
            # Get available expirations
            expirations = ticker.options
            if not expirations:
                return None
            
            # Find expiration closest to target DTE
            today = datetime.now().date()
            best_exp = None
            best_dte_diff = float('inf')
            
            for exp in expirations:
                exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
                dte = (exp_date - today).days
                dte_diff = abs(dte - target_dte)
                
                # For weekly trading (7 DTE), prefer 2-14 day range
                if target_dte <= 7:
                    valid_range = (2, 14)
                else:
                    valid_range = (7, 45)
                
                if valid_range[0] <= dte <= valid_range[1] and dte_diff < best_dte_diff:
                    best_dte_diff = dte_diff
                    best_exp = exp
            
            # Fallback to nearest if no good match
            if best_exp is None:
                best_exp = expirations[0]
            
            exp_date = datetime.strptime(best_exp, '%Y-%m-%d').date()
            actual_dte = (exp_date - today).days
            
            # Get options chain
            chain = ticker.option_chain(best_exp)
            calls = chain.calls.copy()
            puts = chain.puts.copy()
            
            # Current price
            hist = ticker.history(period='5d')
            if hist.empty:
                return None
            current_price = hist['Close'].iloc[-1]
            
            # Calculate historical volatility
            returns = hist['Close'].pct_change().dropna()
            hist_vol = returns.std() * math.sqrt(252) if len(returns) > 0 else 0.3
            
            # Find ATM options
            calls['distance'] = abs(calls['strike'] - current_price)
            puts['distance'] = abs(puts['strike'] - current_price)
            
            if calls.empty or puts.empty:
                return None
            
            atm_call = calls.nsmallest(1, 'distance').iloc[0]
            atm_put = puts.nsmallest(1, 'distance').iloc[0]
            
            # Calculate IV
            avg_iv = (atm_call['impliedVolatility'] + atm_put['impliedVolatility']) / 2
            vol_to_use = avg_iv if avg_iv > 0 else hist_vol
            
            # Put/Call ratio
            total_call_oi = calls['openInterest'].sum()
            total_put_oi = puts['openInterest'].sum()
            pc_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else 0
            
            # Calculate ITM probability and delta for each option
            def calc_itm_probability(row, option_type):
                try:
                    S = current_price
                    K = row['strike']
                    T = actual_dte / 365.0
                    sigma = row['impliedVolatility'] if row['impliedVolatility'] > 0 else vol_to_use
                    
                    if T <= 0 or sigma <= 0:
                        return 0.5
                    
                    d2 = (math.log(S / K) + (-0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
                    
                    def norm_cdf(x):
                        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
                    
                    if option_type == 'call':
                        return norm_cdf(d2)
                    else:
                        return norm_cdf(-d2)
                except:
                    return 0.5
            
            def calc_delta(row, option_type):
                try:
                    S = current_price
                    K = row['strike']
                    T = actual_dte / 365.0
                    sigma = row['impliedVolatility'] if row['impliedVolatility'] > 0 else vol_to_use
                    
                    if T <= 0 or sigma <= 0:
                        return 0.5 if option_type == 'call' else -0.5
                    
                    d1 = (math.log(S / K) + (0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
                    
                    def norm_cdf(x):
                        return 0.5 * (1 + math.erf(x / math.sqrt(2)))
                    
                    if option_type == 'call':
                        return norm_cdf(d1)
                    else:
                        return norm_cdf(d1) - 1
                except:
                    return 0.5 if option_type == 'call' else -0.5
            
            calls['itm_prob'] = calls.apply(lambda r: calc_itm_probability(r, 'call'), axis=1)
            puts['itm_prob'] = puts.apply(lambda r: calc_itm_probability(r, 'put'), axis=1)
            calls['delta'] = calls.apply(lambda r: calc_delta(r, 'call'), axis=1)
            puts['delta'] = puts.apply(lambda r: calc_delta(r, 'put'), axis=1)
            
            # Score options
            def score_option(row, option_type):
                score = 0
                
                # Liquidity: Open Interest
                oi = row['openInterest'] if pd.notna(row['openInterest']) else 0
                if oi >= 500:
                    score += 30
                elif oi >= 100:
                    score += 20
                elif oi >= 50:
                    score += 10
                
                # Liquidity: Volume
                vol = row['volume'] if pd.notna(row['volume']) else 0
                if vol >= 100:
                    score += 20
                elif vol >= 50:
                    score += 10
                
                # Bid-Ask Spread
                if row['ask'] > 0 and row['bid'] > 0:
                    spread_pct = (row['ask'] - row['bid']) / row['ask']
                    if spread_pct <= 0.05:
                        score += 25
                    elif spread_pct <= 0.10:
                        score += 15
                    elif spread_pct <= 0.15:
                        score += 5
                
                # Delta sweet spot
                delta = abs(row['delta'])
                if 0.40 <= delta <= 0.60:
                    score += 25
                elif 0.30 <= delta <= 0.70:
                    score += 20
                elif 0.20 <= delta <= 0.80:
                    score += 10
                
                # ITM Probability
                itm = row['itm_prob']
                if 0.40 <= itm <= 0.60:
                    score += 20
                elif 0.30 <= itm <= 0.70:
                    score += 15
                elif 0.25 <= itm <= 0.75:
                    score += 10
                
                return score
            
            calls['score'] = calls.apply(lambda r: score_option(r, 'call'), axis=1)
            puts['score'] = puts.apply(lambda r: score_option(r, 'put'), axis=1)
            
            # Filter strikes within reasonable range
            call_candidates = calls[
                (calls['strike'] >= current_price * 0.92) & 
                (calls['strike'] <= current_price * 1.15) &
                (calls['openInterest'] >= 10)
            ].copy()
            
            put_candidates = puts[
                (puts['strike'] >= current_price * 0.85) & 
                (puts['strike'] <= current_price * 1.08) &
                (puts['openInterest'] >= 10)
            ].copy()
            
            # Get best options
            best_calls = call_candidates.nlargest(5, 'score') if len(call_candidates) > 0 else pd.DataFrame()
            best_puts = put_candidates.nlargest(5, 'score') if len(put_candidates) > 0 else pd.DataFrame()
            
            # Get preferred strikes
            def get_preferred_strikes(df, current_price, option_type):
                if df.empty:
                    return []
                
                preferred = []
                
                # ITM option
                if option_type == 'call':
                    itm = df[df['strike'] < current_price].nlargest(1, 'score')
                else:
                    itm = df[df['strike'] > current_price].nlargest(1, 'score')
                
                if not itm.empty:
                    row = itm.iloc[0]
                    preferred.append({
                        'type': 'ITM',
                        'strike': row['strike'],
                        'price': (row['bid'] + row['ask']) / 2,
                        'bid': row['bid'],
                        'ask': row['ask'],
                        'delta': row['delta'],
                        'itm_prob': row['itm_prob'],
                        'iv': row['impliedVolatility'],
                        'oi': int(row['openInterest']) if pd.notna(row['openInterest']) else 0,
                        'volume': int(row['volume']) if pd.notna(row['volume']) else 0,
                        'score': row['score'],
                        'reason': 'Higher win probability, lower risk/reward'
                    })
                
                # ATM option
                atm = df.nsmallest(1, 'distance')
                if not atm.empty:
                    row = atm.iloc[0]
                    preferred.append({
                        'type': 'ATM',
                        'strike': row['strike'],
                        'price': (row['bid'] + row['ask']) / 2,
                        'bid': row['bid'],
                        'ask': row['ask'],
                        'delta': row['delta'],
                        'itm_prob': row['itm_prob'],
                        'iv': row['impliedVolatility'],
                        'oi': int(row['openInterest']) if pd.notna(row['openInterest']) else 0,
                        'volume': int(row['volume']) if pd.notna(row['volume']) else 0,
                        'score': row['score'],
                        'reason': 'Balanced risk/reward, highest theta'
                    })
                
                # OTM option
                if option_type == 'call':
                    otm = df[(df['strike'] > current_price * 1.02) & (df['strike'] < current_price * 1.10)].nlargest(1, 'score')
                else:
                    otm = df[(df['strike'] < current_price * 0.98) & (df['strike'] > current_price * 0.90)].nlargest(1, 'score')
                
                if not otm.empty:
                    row = otm.iloc[0]
                    preferred.append({
                        'type': 'OTM',
                        'strike': row['strike'],
                        'price': (row['bid'] + row['ask']) / 2,
                        'bid': row['bid'],
                        'ask': row['ask'],
                        'delta': row['delta'],
                        'itm_prob': row['itm_prob'],
                        'iv': row['impliedVolatility'],
                        'oi': int(row['openInterest']) if pd.notna(row['openInterest']) else 0,
                        'volume': int(row['volume']) if pd.notna(row['volume']) else 0,
                        'score': row['score'],
                        'reason': 'Higher reward potential, lower cost'
                    })
                
                return preferred
            
            preferred_calls = get_preferred_strikes(call_candidates, current_price, 'call')
            preferred_puts = get_preferred_strikes(put_candidates, current_price, 'put')
            
            # Format best options
            def format_options_list(df):
                if df.empty:
                    return []
                return df[['strike', 'lastPrice', 'bid', 'ask', 'volume', 'openInterest', 
                          'impliedVolatility', 'delta', 'itm_prob', 'score']].to_dict('records')
            
            return {
                'expiration': best_exp,
                'dte': actual_dte,
                'target_dte': target_dte,
                'current_price': current_price,
                'iv': avg_iv,
                'hist_vol': hist_vol,
                'pc_ratio': pc_ratio,
                'total_call_oi': total_call_oi,
                'total_put_oi': total_put_oi,
                'atm_call_strike': atm_call['strike'],
                'atm_call_price': (atm_call['bid'] + atm_call['ask']) / 2,
                'atm_put_strike': atm_put['strike'],
                'atm_put_price': (atm_put['bid'] + atm_put['ask']) / 2,
                'preferred_calls': preferred_calls,
                'preferred_puts': preferred_puts,
                'best_calls': format_options_list(best_calls),
                'best_puts': format_options_list(best_puts),
            }
            
        except Exception as e:
            return None
    
    def scan(self, symbols: List[str], min_score: float = 0.0) -> List[Dict]:
        """Scan multiple symbols"""
        results = []
        total = len(symbols)
        
        for i, symbol in enumerate(symbols):
            if (i + 1) % 20 == 0:
                print(f"  Scanning... {i+1}/{total}")
            
            df = self.fetch_data(symbol)
            if df is None or len(df) < 20:
                continue
            
            try:
                analysis = self.analyze(symbol, df)
                if analysis['score'] >= min_score:
                    results.append(analysis)
            except Exception as e:
                continue
        
        # Sort by score
        results.sort(key=lambda x: x['score'], reverse=True)
        return results


# ==================== Display Functions ====================

def print_scan_results(results: List[Dict], top_n: int = 20):
    """Print scan results in a table"""
    
    if not results:
        print(f"\n{C.YELLOW}No results found.{C.END}")
        return
    
    print(f"\n{C.BOLD}{'='*90}{C.END}")
    print(f"{C.BOLD}{'Symbol':<8} {'Price':>10} {'1D':>8} {'1W':>8} {'RSI':>6} {'Vol':>6} {'Score':>7} {'Direction':<10}{C.END}")
    print(f"{'='*90}")
    
    for r in results[:top_n]:
        # Color coding
        if r['direction'] == 'BULLISH':
            dir_color = C.GREEN
        elif r['direction'] == 'BEARISH':
            dir_color = C.RED
        else:
            dir_color = C.YELLOW
        
        change_1d_color = C.GREEN if r['change_1d'] >= 0 else C.RED
        change_1w_color = C.GREEN if r['change_1w'] >= 0 else C.RED
        
        print(f"{r['symbol']:<8} ${r['price']:>9.2f} "
              f"{change_1d_color}{r['change_1d']*100:>+7.2f}%{C.END} "
              f"{change_1w_color}{r['change_1w']*100:>+7.2f}%{C.END} "
              f"{r['rsi']:>6.1f} "
              f"{r['volume_ratio']:>5.1f}x "
              f"{r['score']:>6.2f} "
              f"{dir_color}{r['direction']:<10}{C.END}")
    
    print(f"{'='*90}")


def print_detailed_analysis(result: Dict):
    """Print detailed analysis for a single stock"""
    
    r = result
    dir_color = C.GREEN if r['direction'] == 'BULLISH' else (C.RED if r['direction'] == 'BEARISH' else C.YELLOW)
    
    print(f"\n{C.BOLD}{'='*70}{C.END}")
    print(f"{C.BOLD}   {r['symbol']} - Detailed Analysis{C.END}")
    print(f"{C.BOLD}{'='*70}{C.END}")
    
    print(f"\n{C.BOLD}Price Action{C.END}")
    print(f"  Current Price: ${r['price']:.2f}")
    print(f"  1 Day Change:  {r['change_1d']*100:+.2f}%")
    print(f"  1 Week Change: {r['change_1w']*100:+.2f}%")
    print(f"  1 Month Change: {r['change_1m']*100:+.2f}%")
    
    print(f"\n{C.BOLD}Technical Indicators{C.END}")
    print(f"  RSI:           {r['rsi']:.1f}")
    print(f"  MACD:          {r['macd']:.3f}")
    print(f"  MACD Signal:   {r['macd_signal']:.3f}")
    print(f"  MACD Hist:     {r['macd_hist']:.3f}")
    print(f"  Stochastic K:  {r['stoch_k']:.1f}")
    print(f"  Stochastic D:  {r['stoch_d']:.1f}")
    
    print(f"\n{C.BOLD}Moving Averages{C.END}")
    print(f"  SMA 20:        ${r['sma_20']:.2f}")
    print(f"  SMA 50:        ${r['sma_50']:.2f}")
    if r['sma_200']:
        print(f"  SMA 200:       ${r['sma_200']:.2f}")
    
    print(f"\n{C.BOLD}Volatility{C.END}")
    print(f"  ATR:           ${r['atr']:.2f} ({r['atr_pct']:.1f}%)")
    print(f"  Bollinger Upper: ${r['bb_upper']:.2f}")
    print(f"  Bollinger Lower: ${r['bb_lower']:.2f}")
    
    print(f"\n{C.BOLD}Volume{C.END}")
    print(f"  Volume:        {r['volume']:,.0f}")
    print(f"  Volume Ratio:  {r['volume_ratio']:.2f}x average")
    
    print(f"\n{C.BOLD}Signals{C.END}")
    for signal, direction, strength in r['signals']:
        sig_color = C.GREEN if direction == 'bullish' else C.RED
        print(f"  {sig_color}• {signal}{C.END}")
    
    print(f"\n{C.BOLD}Overall Assessment{C.END}")
    print(f"  Direction:     {dir_color}{r['direction']}{C.END}")
    print(f"  Score:         {r['score']:.2f}")
    print(f"  Bullish Score: {r['bullish_score']}")
    print(f"  Bearish Score: {r['bearish_score']}")
    
    print(f"\n{C.BOLD}Trade Setup{C.END}")
    print(f"  Stop Loss:     ${r['stop_loss']:.2f} ({(r['stop_loss']/r['price']-1)*100:+.1f}%)")
    print(f"  Target:        ${r['target']:.2f} ({(r['target']/r['price']-1)*100:+.1f}%)")
    print(f"  Risk/Reward:   {r['risk_reward']:.2f}")


def print_options_analysis(symbol: str, options_data: Dict, direction: str):
    """Print options analysis with preferred strikes"""
    
    if not options_data:
        print(f"\n{C.YELLOW}No options data available for {symbol}{C.END}")
        return
    
    o = options_data
    
    # Determine period label
    if o['target_dte'] <= 7:
        period_label = "1 WEEK TRADING PERIOD"
    elif o['target_dte'] <= 14:
        period_label = "2 WEEK TRADING PERIOD"
    else:
        period_label = f"{o['target_dte']} DAY TRADING PERIOD"
    
    print(f"\n{C.BOLD}{'='*70}{C.END}")
    print(f"{C.BOLD}OPTIONS ANALYSIS - {period_label}{C.END}")
    print(f"{C.BOLD}{'='*70}{C.END}")
    
    print(f"\n{C.BOLD}Expiration & Volatility{C.END}")
    print(f"  Target DTE:      {o['target_dte']} days")
    print(f"  Expiration:      {o['expiration']} ({o['dte']} DTE)")
    print(f"  Current Price:   ${o['current_price']:.2f}")
    print(f"  Implied Vol:     {o['iv']*100:.1f}%")
    print(f"  Historical Vol:  {o['hist_vol']*100:.1f}%")
    print(f"  Put/Call Ratio:  {o['pc_ratio']:.2f}")
    
    print(f"\n{C.BOLD}Open Interest{C.END}")
    print(f"  Total Call OI:   {o['total_call_oi']:,}")
    print(f"  Total Put OI:    {o['total_put_oi']:,}")
    
    print(f"\n{C.BOLD}ATM Options{C.END}")
    print(f"  ATM Call: ${o['atm_call_strike']:.2f} @ ${o['atm_call_price']:.2f}")
    print(f"  ATM Put:  ${o['atm_put_strike']:.2f} @ ${o['atm_put_price']:.2f}")
    
    # Show preferred strikes based on direction
    if direction == 'BULLISH':
        print(f"\n{C.BOLD}{C.GREEN}{'='*70}{C.END}")
        print(f"{C.BOLD}{C.GREEN}★ PREFERRED CALL STRIKES (Bullish Signal){C.END}")
        print(f"{C.BOLD}{C.GREEN}{'='*70}{C.END}")
        
        if o['preferred_calls']:
            for pc in o['preferred_calls']:
                type_color = C.GREEN if pc['type'] == 'ITM' else (C.YELLOW if pc['type'] == 'ATM' else C.BLUE)
                print(f"\n  {type_color}{C.BOLD}[{pc['type']}] ${pc['strike']:.2f} CALL{C.END}")
                print(f"      Price:        ${pc['price']:.2f} (Bid: ${pc['bid']:.2f} / Ask: ${pc['ask']:.2f})")
                print(f"      Delta:        {pc['delta']:.2f}")
                print(f"      ITM Prob:     {pc['itm_prob']*100:.1f}%")
                print(f"      IV:           {pc['iv']*100:.1f}%")
                print(f"      Open Interest: {pc['oi']:,}")
                print(f"      Volume:       {pc['volume']:,}")
                print(f"      Score:        {pc['score']:.0f}/100")
                print(f"      {C.YELLOW}→ {pc['reason']}{C.END}")
        else:
            print(f"  {C.YELLOW}No suitable call options found{C.END}")
    
    elif direction == 'BEARISH':
        print(f"\n{C.BOLD}{C.RED}{'='*70}{C.END}")
        print(f"{C.BOLD}{C.RED}★ PREFERRED PUT STRIKES (Bearish Signal){C.END}")
        print(f"{C.BOLD}{C.RED}{'='*70}{C.END}")
        
        if o['preferred_puts']:
            for pp in o['preferred_puts']:
                type_color = C.GREEN if pp['type'] == 'ITM' else (C.YELLOW if pp['type'] == 'ATM' else C.BLUE)
                print(f"\n  {type_color}{C.BOLD}[{pp['type']}] ${pp['strike']:.2f} PUT{C.END}")
                print(f"      Price:        ${pp['price']:.2f} (Bid: ${pp['bid']:.2f} / Ask: ${pp['ask']:.2f})")
                print(f"      Delta:        {pp['delta']:.2f}")
                print(f"      ITM Prob:     {pp['itm_prob']*100:.1f}%")
                print(f"      IV:           {pp['iv']*100:.1f}%")
                print(f"      Open Interest: {pp['oi']:,}")
                print(f"      Volume:       {pp['volume']:,}")
                print(f"      Score:        {pp['score']:.0f}/100")
                print(f"      {C.YELLOW}→ {pp['reason']}{C.END}")
        else:
            print(f"  {C.YELLOW}No suitable put options found{C.END}")
    
    else:
        print(f"\n{C.BOLD}{C.YELLOW}{'='*70}{C.END}")
        print(f"{C.BOLD}{C.YELLOW}PREFERRED STRIKES (Neutral - Showing Both){C.END}")
        print(f"{C.BOLD}{C.YELLOW}{'='*70}{C.END}")
        
        if o['preferred_calls']:
            print(f"\n  {C.BOLD}Calls:{C.END}")
            for pc in o['preferred_calls'][:2]:
                print(f"    [{pc['type']}] ${pc['strike']:.2f} @ ${pc['price']:.2f} | Delta: {pc['delta']:.2f} | ITM: {pc['itm_prob']*100:.0f}%")
        
        if o['preferred_puts']:
            print(f"\n  {C.BOLD}Puts:{C.END}")
            for pp in o['preferred_puts'][:2]:
                print(f"    [{pp['type']}] ${pp['strike']:.2f} @ ${pp['price']:.2f} | Delta: {pp['delta']:.2f} | ITM: {pp['itm_prob']*100:.0f}%")
    
    # Trading recommendation
    if o['target_dte'] <= 7:
        rec_label = "WEEKLY"
    elif o['target_dte'] <= 14:
        rec_label = "2-WEEK"
    else:
        rec_label = f"{o['target_dte']}-DAY"
    
    print(f"\n{C.BOLD}{'='*70}{C.END}")
    print(f"{C.BOLD}{rec_label} TRADING RECOMMENDATION{C.END}")
    print(f"{C.BOLD}{'='*70}{C.END}")
    
    if direction == 'BULLISH' and o['preferred_calls']:
        best = o['preferred_calls'][0]
        print(f"\n  {C.GREEN}{C.BOLD}BUY CALL:{C.END} ${best['strike']:.2f} strike @ ${best['price']:.2f}")
        print(f"  Expiration: {o['expiration']} ({o['dte']} days)")
        print(f"  Max Risk: ${best['price'] * 100:.2f} per contract")
        breakeven = best['strike'] + best['price']
        print(f"  Breakeven: ${breakeven:.2f} ({(breakeven/o['current_price']-1)*100:+.1f}%)")
        print(f"  ITM Probability: {best['itm_prob']*100:.1f}%")
        
    elif direction == 'BEARISH' and o['preferred_puts']:
        best = o['preferred_puts'][0]
        print(f"\n  {C.RED}{C.BOLD}BUY PUT:{C.END} ${best['strike']:.2f} strike @ ${best['price']:.2f}")
        print(f"  Expiration: {o['expiration']} ({o['dte']} days)")
        print(f"  Max Risk: ${best['price'] * 100:.2f} per contract")
        breakeven = best['strike'] - best['price']
        print(f"  Breakeven: ${breakeven:.2f} ({(breakeven/o['current_price']-1)*100:+.1f}%)")
        print(f"  ITM Probability: {best['itm_prob']*100:.1f}%")
    
    else:
        print(f"\n  {C.YELLOW}Signal is neutral - consider waiting for clearer direction{C.END}")
        print(f"  Or use a neutral strategy like iron condor or strangle")


def find_best_options(scanner: StockScanner, top_n: int = 10, target_dte: int = 7, direction_filter: str = None):
    """Scan entire market and find the best options opportunities."""
    
    print(f"\n{C.BOLD}{C.BLUE}{'='*80}{C.END}")
    print(f"{C.BOLD}{C.BLUE}   FULL MARKET OPTIONS SCANNER - Finding Best Opportunities{C.END}")
    print(f"{C.BOLD}{C.BLUE}{'='*80}{C.END}")
    
    print(f"\n{C.BOLD}Scanning across:{C.END}")
    print(f"  • DOW 30:       {SYMBOL_COUNTS['DOW']} stocks")
    print(f"  • NASDAQ 100:   {SYMBOL_COUNTS['NASDAQ']} stocks")
    print(f"  • S&P 500:      {SYMBOL_COUNTS['SP500']} stocks")
    print(f"  • Russell 2000: {SYMBOL_COUNTS['RUSSELL']} stocks")
    print(f"  • ETFs:         {SYMBOL_COUNTS['ETFs']} ETFs")
    print(f"  • Total Unique: {SYMBOL_COUNTS['TOTAL']} symbols")
    print(f"\n  Target DTE: {target_dte} days")
    
    # Phase 1: Quick scan all symbols
    print(f"\n{C.YELLOW}Phase 1: Technical analysis across all symbols...{C.END}")
    
    all_results = []
    total = len(FULL_MARKET)
    failed = 0
    
    for i, symbol in enumerate(FULL_MARKET):
        if (i + 1) % 50 == 0:
            print(f"  Scanned {i+1}/{total} symbols... (found {len(all_results)} candidates)")
        
        df = scanner.fetch_data(symbol)
        if df is None or len(df) < 20:
            failed += 1
            continue
        
        try:
            analysis = scanner.analyze(symbol, df)
            # Lower threshold to 0.45 to find more opportunities
            if analysis['score'] >= 0.45:
                all_results.append(analysis)
        except Exception as e:
            failed += 1
            continue
    
    print(f"  Scanned {total} symbols, {failed} failed, found {len(all_results)} with score >= 0.45")
    
    # Filter by direction
    if direction_filter == 'bullish':
        all_results = [r for r in all_results if r['direction'] == 'BULLISH']
        print(f"  Filtered to {len(all_results)} bullish signals")
    elif direction_filter == 'bearish':
        all_results = [r for r in all_results if r['direction'] == 'BEARISH']
        print(f"  Filtered to {len(all_results)} bearish signals")
    
    # Sort by score
    all_results.sort(key=lambda x: x['score'], reverse=True)
    
    # Phase 2: Options analysis
    print(f"\n{C.YELLOW}Phase 2: Options analysis for top {min(top_n * 2, len(all_results))} candidates...{C.END}")
    
    options_candidates = []
    
    for r in all_results[:top_n * 2]:
        options = scanner.get_options_data(r['symbol'], target_dte=target_dte)
        if options:
            opt_score = 0
            
            if r['direction'] == 'BULLISH' and options.get('preferred_calls'):
                best = options['preferred_calls'][0]
                opt_score = best.get('score', 0)
                r['option_type'] = 'CALL'
                r['strike'] = best['strike']
                r['option_price'] = best['price']
                r['delta'] = best['delta']
                r['itm_prob'] = best['itm_prob']
                r['expiration'] = options['expiration']
                r['dte'] = options['dte']
                r['iv'] = options['iv']
                r['option_score'] = opt_score
                
            elif r['direction'] == 'BEARISH' and options.get('preferred_puts'):
                best = options['preferred_puts'][0]
                opt_score = best.get('score', 0)
                r['option_type'] = 'PUT'
                r['strike'] = best['strike']
                r['option_price'] = best['price']
                r['delta'] = best['delta']
                r['itm_prob'] = best['itm_prob']
                r['expiration'] = options['expiration']
                r['dte'] = options['dte']
                r['iv'] = options['iv']
                r['option_score'] = opt_score
            
            if opt_score > 0:
                r['combined_score'] = r['score'] * 0.6 + (opt_score / 100) * 0.4
                options_candidates.append(r)
    
    # Sort by combined score
    options_candidates.sort(key=lambda x: x.get('combined_score', 0), reverse=True)
    
    return options_candidates[:top_n]


def print_best_options(candidates: List[Dict]):
    """Print best options opportunities"""
    
    if not candidates:
        print(f"\n{C.YELLOW}{'='*60}{C.END}")
        print(f"{C.YELLOW}No suitable options opportunities found.{C.END}")
        print(f"{C.YELLOW}{'='*60}{C.END}")
        print(f"\nPossible reasons:")
        print(f"  1. Market is closed (weekends/holidays)")
        print(f"  2. No strong signals currently (neutral market)")
        print(f"  3. Internet/data connection issues")
        print(f"\nTry:")
        print(f"  - python scanner.py --debug          (test connection)")
        print(f"  - python scanner.py -s AAPL --deep   (test single stock)")
        print(f"  - python scanner.py --sector tech    (scan smaller list)")
        return
    
    print(f"\n{C.BOLD}{C.GREEN}{'='*80}{C.END}")
    print(f"{C.BOLD}{C.GREEN}   🎯 TOP {len(candidates)} OPTIONS OPPORTUNITIES - WEEKLY TRADES{C.END}")
    print(f"{C.BOLD}{C.GREEN}{'='*80}{C.END}")
    
    for i, c in enumerate(candidates, 1):
        direction_color = C.GREEN if c['direction'] == 'BULLISH' else C.RED
        opt_type = c.get('option_type', 'N/A')
        
        print(f"\n{C.BOLD}#{i} {c['symbol']} - {direction_color}{c['direction']} {opt_type}{C.END}")
        print(f"    {'─'*60}")
        
        print(f"    Stock Price:     ${c['price']:.2f} ({c['change_1d']*100:+.2f}% today)")
        print(f"    Technical Score: {c['score']:.2f}")
        print(f"    RSI:             {c['rsi']:.1f}")
        print(f"    Volume Ratio:    {c['volume_ratio']:.2f}x")
        
        if 'strike' in c:
            print(f"\n    {C.BOLD}Recommended Option:{C.END}")
            print(f"    {direction_color}{opt_type} ${c['strike']:.2f}{C.END} @ ${c['option_price']:.2f}")
            print(f"    Expiration:      {c['expiration']} ({c['dte']} DTE)")
            print(f"    Delta:           {c['delta']:.2f}")
            print(f"    ITM Probability: {c['itm_prob']*100:.1f}%")
            print(f"    IV:              {c['iv']*100:.1f}%")
            
            cost = c['option_price'] * 100
            if opt_type == 'CALL':
                breakeven = c['strike'] + c['option_price']
                move_needed = (breakeven / c['price'] - 1) * 100
            else:
                breakeven = c['strike'] - c['option_price']
                move_needed = (1 - breakeven / c['price']) * 100
            
            print(f"\n    {C.BOLD}Trade Setup:{C.END}")
            print(f"    Cost per contract: ${cost:.2f}")
            print(f"    Breakeven:         ${breakeven:.2f} ({move_needed:+.1f}%)")
            print(f"    Combined Score:    {c.get('combined_score', 0):.2f}")
        
        # Show signals
        bull_signals = [s[0] for s in c['signals'] if s[1] == 'bullish'][:3]
        bear_signals = [s[0] for s in c['signals'] if s[1] == 'bearish'][:3]
        
        if bull_signals:
            print(f"\n    {C.GREEN}Bullish: {', '.join(bull_signals)}{C.END}")
        if bear_signals:
            print(f"    {C.RED}Bearish: {', '.join(bear_signals)}{C.END}")
    
    # Summary table
    print(f"\n{C.BOLD}{'='*80}{C.END}")
    print(f"{C.BOLD}SUMMARY TABLE{C.END}")
    print(f"{'='*80}")
    print(f"{'#':<3} {'Symbol':<8} {'Type':<6} {'Strike':>8} {'Price':>8} {'DTE':>5} {'ITM%':>7} {'Delta':>7} {'Score':>7}")
    print(f"{'-'*80}")
    
    for i, c in enumerate(candidates, 1):
        opt_type = c.get('option_type', '-')
        color = C.GREEN if c['direction'] == 'BULLISH' else C.RED
        
        print(f"{i:<3} {color}{c['symbol']:<8}{C.END} {opt_type:<6} "
              f"${c.get('strike', 0):>7.2f} ${c.get('option_price', 0):>7.2f} "
              f"{c.get('dte', 0):>5} {c.get('itm_prob', 0)*100:>6.1f}% "
              f"{c.get('delta', 0):>6.2f} {c.get('combined_score', 0):>6.2f}")
    
    print(f"{'='*80}")
    print(f"\n{C.YELLOW}⚠ This is analysis only. Execute trades at your own risk.{C.END}")


def export_results(results: List[Dict], filename: str):
    """Export results to CSV"""
    
    export_data = []
    for r in results:
        export_data.append({
            'Symbol': r['symbol'],
            'Price': r['price'],
            'Change_1D': r['change_1d'],
            'Change_1W': r['change_1w'],
            'Change_1M': r['change_1m'],
            'RSI': r['rsi'],
            'MACD': r['macd'],
            'Stoch_K': r['stoch_k'],
            'Volume_Ratio': r['volume_ratio'],
            'ATR_Pct': r['atr_pct'],
            'Score': r['score'],
            'Direction': r['direction'],
            'Stop_Loss': r['stop_loss'],
            'Target': r['target'],
            'Risk_Reward': r['risk_reward'],
            'Signals': '; '.join([s[0] for s in r['signals']]),
        })
    
    df = pd.DataFrame(export_data)
    df.to_csv(filename, index=False)
    print(f"\n{C.GREEN}Results exported to {filename}{C.END}")


# ==================== Main ====================

def main():
    parser = argparse.ArgumentParser(
        description='HyperTrader Standalone Scanner - Find the best options opportunities',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scanner.py                      # Scan default symbols
  python scanner.py --best               # Find BEST options across all markets
  python scanner.py --best --top 10      # Top 10 best options
  python scanner.py -s AAPL,TSLA,NVDA    # Scan specific symbols
  python scanner.py --sector nasdaq      # Scan NASDAQ 100
  python scanner.py --sector dow         # Scan Dow 30
  python scanner.py --sector sp500       # Scan S&P 500
  python scanner.py --sector russell     # Scan Russell 2000
  python scanner.py --sector etfs        # Scan all ETFs
  python scanner.py -s AAPL --deep       # Deep analysis with options
  python scanner.py --bullish --top 10   # Top 10 bullish signals
  python scanner.py --export out.csv     # Export to CSV
        """
    )
    
    parser.add_argument('-s', '--symbols', help='Comma-separated symbols to scan')
    parser.add_argument('--best', action='store_true', help='Find BEST options across DOW, NASDAQ, S&P, Russell & ETFs')
    parser.add_argument('--sector', choices=list(WATCHLIST.keys()), help='Scan specific index/sector')
    parser.add_argument('--top', type=int, default=20, help='Number of results to show')
    parser.add_argument('--min-score', type=float, default=0.0, help='Minimum score filter')
    parser.add_argument('--bullish', action='store_true', help='Show only bullish signals')
    parser.add_argument('--bearish', action='store_true', help='Show only bearish signals')
    parser.add_argument('--deep', action='store_true', help='Deep analysis with options data')
    parser.add_argument('--dte', type=int, default=7, help='Target days to expiration (default: 7)')
    parser.add_argument('--export', help='Export results to CSV file')
    parser.add_argument('--debug', action='store_true', help='Show debug information')
    
    args = parser.parse_args()
    
    # Debug mode
    if args.debug:
        print(f"{C.YELLOW}DEBUG MODE ENABLED{C.END}")
        print(f"Testing data connection...")
        try:
            import yfinance as yf
            ticker = yf.Ticker('AAPL')
            df = ticker.history(period='5d')
            if df is not None and len(df) > 0:
                print(f"{C.GREEN}✓ Data connection working - AAPL last price: ${df['Close'].iloc[-1]:.2f}{C.END}")
            else:
                print(f"{C.RED}✗ No data returned for AAPL - check internet connection{C.END}")
                sys.exit(1)
        except Exception as e:
            print(f"{C.RED}✗ Data connection failed: {e}{C.END}")
            sys.exit(1)
    
    args = parser.parse_args()
    
    print(f"""
{C.BOLD}{C.BLUE}
╔═══════════════════════════════════════════════════════════════════════╗
║              HyperTrader Standalone Scanner                           ║
║        Scanning DOW, NASDAQ, S&P 500, Russell 2000 & ETFs            ║
╚═══════════════════════════════════════════════════════════════════════╝
{C.END}
    Scan Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    API Keys: Alpha Vantage ✓, Finnhub ✓
    """)
    
    # Initialize scanner
    scanner = StockScanner()
    
    # Best options mode
    if args.best:
        direction = None
        if args.bullish:
            direction = 'bullish'
        elif args.bearish:
            direction = 'bearish'
        
        best_options = find_best_options(
            scanner, 
            top_n=args.top, 
            target_dte=args.dte,
            direction_filter=direction
        )
        print_best_options(best_options)
        
        if args.export and best_options:
            export_data = []
            for c in best_options:
                export_data.append({
                    'Symbol': c['symbol'],
                    'Direction': c['direction'],
                    'Option_Type': c.get('option_type', ''),
                    'Strike': c.get('strike', ''),
                    'Option_Price': c.get('option_price', ''),
                    'Expiration': c.get('expiration', ''),
                    'DTE': c.get('dte', ''),
                    'Delta': c.get('delta', ''),
                    'ITM_Prob': c.get('itm_prob', ''),
                    'IV': c.get('iv', ''),
                    'Stock_Price': c['price'],
                    'Technical_Score': c['score'],
                    'Combined_Score': c.get('combined_score', ''),
                })
            df = pd.DataFrame(export_data)
            df.to_csv(args.export, index=False)
            print(f"\n{C.GREEN}Results exported to {args.export}{C.END}")
        
        if sys.platform == 'win32':
            input("\nPress Enter to exit...")
        return
    
    # Determine symbols to scan
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(',')]
    elif args.sector:
        symbols = WATCHLIST[args.sector]
        print(f"Scanning {args.sector.upper()}: {len(symbols)} symbols")
    else:
        symbols = WATCHLIST['tech'] + WATCHLIST['financials'] + WATCHLIST['etfs']
        symbols = list(set(symbols))
        print(f"Scanning default watchlist: {len(symbols)} symbols")
    
    print(f"\n{C.BLUE}Fetching data and analyzing...{C.END}\n")
    
    results = scanner.scan(symbols, min_score=args.min_score)
    
    # Filter by direction
    if args.bullish:
        results = [r for r in results if r['direction'] == 'BULLISH']
    elif args.bearish:
        results = [r for r in results if r['direction'] == 'BEARISH']
    
    # Deep analysis for single symbol
    if args.deep and args.symbols and len(args.symbols.split(',')) == 1:
        if results:
            print_detailed_analysis(results[0])
            options_data = scanner.get_options_data(results[0]['symbol'], target_dte=args.dte)
            print_options_analysis(results[0]['symbol'], options_data, results[0]['direction'])
    else:
        print_scan_results(results, args.top)
    
    # Export
    if args.export:
        export_results(results, args.export)
    
    print(f"\n{C.BLUE}Scan complete.{C.END}")
    print(f"{C.YELLOW}Remember: This is analysis only - execute trades manually in your broker.{C.END}\n")
    
    if sys.platform == 'win32':
        input("Press Enter to exit...")


if __name__ == '__main__':
    main()
