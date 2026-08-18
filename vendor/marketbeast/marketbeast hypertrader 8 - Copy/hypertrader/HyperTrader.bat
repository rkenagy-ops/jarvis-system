@echo off
title HyperTrader Menu
cd /d "%~dp0"

:MENU
cls
echo.
echo  ╔═══════════════════════════════════════════════════════════╗
echo  ║              HyperTrader - Trading Scanner                ║
echo  ║        DOW / NASDAQ / S^&P 500 / Russell / ETFs           ║
echo  ╚═══════════════════════════════════════════════════════════╝
echo.
echo     1. ★ BEST OPTIONS (Full Market Scan) ★
echo     2. Scan Specific Symbols
echo     3. Deep Analysis (single stock + options)
echo     4. Scan DOW 30
echo     5. Scan NASDAQ 100
echo     6. Scan S^&P 500 Top 100
echo     7. Scan Russell 2000
echo     8. Scan All ETFs
echo     9. Bullish Signals Only
echo     A. Bearish Signals Only
echo     B. Export to CSV
echo     C. Install/Update Dependencies
echo     0. Exit
echo.
set /p CHOICE="Select option (0-9, A-C): "

if "%CHOICE%"=="1" goto BEST_OPTIONS
if "%CHOICE%"=="2" goto CUSTOM_SCAN
if "%CHOICE%"=="3" goto DEEP_ANALYSIS
if "%CHOICE%"=="4" goto DOW_SCAN
if "%CHOICE%"=="5" goto NASDAQ_SCAN
if "%CHOICE%"=="6" goto SP500_SCAN
if "%CHOICE%"=="7" goto RUSSELL_SCAN
if "%CHOICE%"=="8" goto ETF_SCAN
if "%CHOICE%"=="9" goto BULLISH_SCAN
if /i "%CHOICE%"=="A" goto BEARISH_SCAN
if /i "%CHOICE%"=="B" goto EXPORT
if /i "%CHOICE%"=="C" goto INSTALL
if "%CHOICE%"=="0" goto EXIT

echo Invalid option. Try again.
timeout /t 2 >nul
goto MENU

:BEST_OPTIONS
echo.
echo ============================================================
echo   Finding BEST OPTIONS across all indices and ETFs...
echo   This will scan 250+ symbols - please wait...
echo ============================================================
echo.
set /p TOPN="How many top picks? (default 10): "
if "%TOPN%"=="" set TOPN=10
python scanner.py --best --top %TOPN%
goto PAUSE_AND_MENU

:CUSTOM_SCAN
echo.
set /p SYMBOLS="Enter symbols (comma-separated): "
if "%SYMBOLS%"=="" goto MENU
echo.
python scanner.py -s %SYMBOLS%
goto PAUSE_AND_MENU

:DEEP_ANALYSIS
echo.
set /p SYMBOL="Enter symbol for deep analysis: "
if "%SYMBOL%"=="" goto MENU
echo.
set /p DTE="Target DTE (default 7 for weekly): "
if "%DTE%"=="" set DTE=7
echo.
python scanner.py -s %SYMBOL% --deep --dte %DTE%
goto PAUSE_AND_MENU

:DOW_SCAN
echo.
echo Scanning DOW 30 stocks...
python scanner.py --sector dow
goto PAUSE_AND_MENU

:NASDAQ_SCAN
echo.
echo Scanning NASDAQ 100 stocks...
python scanner.py --sector nasdaq
goto PAUSE_AND_MENU

:SP500_SCAN
echo.
echo Scanning S^&P 500 Top 100 stocks...
python scanner.py --sector sp500
goto PAUSE_AND_MENU

:RUSSELL_SCAN
echo.
echo Scanning Russell 2000 top stocks...
python scanner.py --sector russell
goto PAUSE_AND_MENU

:ETF_SCAN
echo.
echo Scanning all ETFs...
python scanner.py --sector etfs
goto PAUSE_AND_MENU

:BULLISH_SCAN
echo.
echo Finding best BULLISH opportunities...
python scanner.py --best --bullish --top 15
goto PAUSE_AND_MENU

:BEARISH_SCAN
echo.
echo Finding best BEARISH opportunities...
python scanner.py --best --bearish --top 15
goto PAUSE_AND_MENU

:EXPORT
echo.
set /p FILENAME="Enter filename (default: best_options.csv): "
if "%FILENAME%"=="" set FILENAME=best_options.csv
python scanner.py --best --top 20 --export %FILENAME%
echo File saved: %FILENAME%
goto PAUSE_AND_MENU

:INSTALL
echo.
echo Installing/updating dependencies...
pip install --upgrade pandas numpy yfinance ib_insync scipy scikit-learn requests
echo.
echo Dependencies installed.
goto PAUSE_AND_MENU

:PAUSE_AND_MENU
echo.
echo ================================================================
pause
goto MENU

:EXIT
echo.
echo Goodbye!
timeout /t 2 >nul
exit /b 0
