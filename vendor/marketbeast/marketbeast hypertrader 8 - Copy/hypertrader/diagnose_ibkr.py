"""
IBKR Connection Diagnostic Tool
"""

import socket
import sys
import time

def check_port(host, port, timeout=5):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

def main():
    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║           IBKR Connection Diagnostic Tool                             ║
╚═══════════════════════════════════════════════════════════════════════╝
    """)
    
    ports = {
        7496: "TWS Live Trading",
        7497: "TWS Paper Trading",
        4001: "IB Gateway Live",
        4002: "IB Gateway Paper",
    }
    
    print("Step 1: Checking if TWS/Gateway ports are open...\n")
    
    open_ports = []
    for port, desc in ports.items():
        is_open = check_port("127.0.0.1", port)
        status = "✓ OPEN" if is_open else "✗ CLOSED"
        color = "\033[92m" if is_open else "\033[91m"
        print(f"  Port {port} ({desc}): {color}{status}\033[0m")
        if is_open:
            open_ports.append(port)
    
    print()
    
    if not open_ports:
        print("""
\033[91m════════════════════════════════════════════════════════════════════════
  NO IBKR PORTS ARE OPEN - TWS/Gateway API is not accepting connections
════════════════════════════════════════════════════════════════════════\033[0m

\033[93m>>> FOLLOW THESE STEPS IN TWS: <<<\033[0m

  1. Open TWS and LOG IN completely
  
  2. Go to: Edit → Global Configuration → API → Settings
  
  3. CHECK these boxes:
     ☑ Enable ActiveX and Socket Clients
     
  4. Set Socket Port: 7497 (paper) or 7496 (live)
     
  5. In "Trusted IPs" add: 127.0.0.1
     
  6. Click "Apply" then "OK"
  
  7. RESTART TWS completely
  
  8. Run this diagnostic again
""")
    else:
        print(f"\033[92m✓ Found open port(s): {open_ports}\033[0m\n")
        
        print("Step 2: Testing ib_insync connection...\n")
        
        try:
            from ib_insync import IB, util
            util.logToConsole(level=40)
            
            ib = IB()
            
            for port in open_ports:
                print(f"  Trying port {port}...", end=" ")
                try:
                    ib.connect('127.0.0.1', port, clientId=99, timeout=10)
                    print(f"\033[92mCONNECTED!\033[0m")
                    
                    print(f"\n\033[92m════════════════════════════════════════════════════════════════════════")
                    print(f"  SUCCESS! Connected to IBKR")
                    print(f"════════════════════════════════════════════════════════════════════════\033[0m")
                    
                    accounts = ib.managedAccounts()
                    print(f"\n  Account(s): {accounts}")
                    
                    if accounts:
                        ib.reqAccountSummary()
                        time.sleep(1)
                        summary = ib.accountSummary()
                        
                        for item in summary:
                            if item.tag in ['NetLiquidation', 'TotalCashValue', 'BuyingPower']:
                                print(f"  {item.tag}: ${float(item.value):,.2f}")
                    
                    print(f"\n  \033[92mYour connection is working!\033[0m")
                    print(f"  Use port {port} in HyperTrader.")
                    
                    ib.disconnect()
                    break
                    
                except Exception as e:
                    print(f"\033[91mFailed: {str(e)[:50]}\033[0m")
                    
        except ImportError:
            print("""
  \033[91mib_insync is not installed.\033[0m
  
  Install it with: pip install ib_insync
""")
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
