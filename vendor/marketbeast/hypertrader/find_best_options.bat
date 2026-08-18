@echo off
title HyperTrader - Best Options Scanner
cd /d "%~dp0"

echo.
echo  ╔═══════════════════════════════════════════════════════════╗
echo  ║       HyperTrader - BEST OPTIONS MARKET SCANNER           ║
echo  ║                                                           ║
echo  ║   Scanning: DOW 30, NASDAQ 100, S^&P 500, Russell 2000    ║
echo  ║             + 60 ETFs (250+ total symbols)                ║
echo  ╚═══════════════════════════════════════════════════════════╝
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from python.org
    pause
    exit /b 1
)

REM Check dependencies
python -c "import pandas, numpy, yfinance" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install pandas numpy yfinance
)

echo How many top picks would you like?
set /p TOPN="Enter number (default 10): "
if "%TOPN%"=="" set TOPN=10

echo.
echo Direction filter:
echo   1. All (bullish + bearish)
echo   2. Bullish only
echo   3. Bearish only
set /p DIRECTION="Select (1-3, default 1): "

set DIRECTION_FLAG=
if "%DIRECTION%"=="2" set DIRECTION_FLAG=--bullish
if "%DIRECTION%"=="3" set DIRECTION_FLAG=--bearish

echo.
echo ================================================================
echo   Scanning entire market... Please wait (2-3 minutes)
echo ================================================================
echo.

python scanner.py --best --top %TOPN% %DIRECTION_FLAG%

echo.
pause
