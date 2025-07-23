from EACommunicator_API import EACommunicator_API
from datetime import datetime, timedelta

if __name__ == "__main__":
    # Initialize the API
 
    api = EACommunicator_API()
    
    # Connect to MT4 EA (replace 'localhost' with the IP if running remotely)
    api.Connect(server='localhost', port=5555)
    
    try:
        # Get account balance (from closed trades)
        balance = api.Get_account_balance()
        print(f"Account Balance: {balance:.2f}")
        
        # Get floating P/L (from open trades)
        floating_pl = api.Get_floating_pl()
        print(f"Floating P/L: {floating_pl:.2f}")
        
        # Get current equity (balance + floating P/L)
        equity = api.Get_current_equity()
        print(f"Current Equity: {equity:.2f}")

        now = datetime.now()
        start_of_day = datetime(now.year, now.month, now.day)
        # start = datetime.strptime("2025-07-21 00:30", "%Y-%m-%d %H:%M")
        # end = datetime.strptime("2025-07-21 02:30", "%Y-%m-%d %H:%M")

   

        closed_pl_today = api.Get_closed_pl_today(timezone_offset=3)  # Adjust for timezone if needed
        print(f"Closed Profit/Loss today: ${closed_pl_today}")
        
    finally:
        # Disconnect when done
        api.Disconnect()   