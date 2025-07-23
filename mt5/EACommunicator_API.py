
from enum import Enum
import json
import zmq
import pandas as pd
from datetime import datetime, timedelta, time
from io import StringIO

class TradingCommands(Enum):
    GET_OPEN_POSITIONS = 9
    GET_CLOSED_POSITIONS = 10

class EACommunicator_API:
    
    contextManager = None
    connected = False
    
    def __init__(self):
        # Socket to talk to the server
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)

    def Disconnect(self):
        """
        Closes the socket connection to a MT4 or MT5 EA bot.
        """
        print(f"Sending DISCONNECT command")
        self.socket.send_string("break^")
        self.socket.close()
        self.context.term()
        return True

    def Connect(self, server: str = 'localhost', port: int = 5555) -> bool:

        self.contextManager = self.socket.connect("tcp://{}:{}".format(server, port)) 

    def Get_account_balance(self) -> float:
        """
        Retrieves the current account balance by summing up all closed positions.
        Returns:
            float: Account balance
        """
        closed_positions = self.Get_all_closed_positions()
        if closed_positions is not None and not closed_positions.empty:
            return closed_positions['profit'].sum()
        return 0.0
    
    

    def Get_current_equity(self) -> float:
        """
        Retrieves the current account equity (balance + floating P/L).
        Returns:
            float: Account equity
        """
        balance = self.Get_account_balance()
        floating_pl = self.Get_floating_pl()
        return balance + floating_pl

    def Get_floating_pl(self) -> float:
        """
        Retrieves the current floating profit/loss from all open positions.
        Returns:
            float: Floating P/L
        """
        open_positions = self.Get_all_open_positions()
        if open_positions is not None and not open_positions.empty:
            return open_positions['profit'].sum()
        return 0.0

    def Get_all_open_positions(self) -> pd.DataFrame:
        """
        Retrieves all open positions, market orders for MT4.
        Returns:
            DataFrame with all position information including profit
        """
        csvReply = self.send_command(TradingCommands.GET_OPEN_POSITIONS)
        df = self.readCsv(csvReply)
        return df

    def Get_all_closed_positions(self) -> pd.DataFrame:
        """Retrieves all closed positions/orders."""
        csvReply = self.send_command(TradingCommands.GET_CLOSED_POSITIONS)
        print("RAW RESPONSE FROM EA:", csvReply)
        df = self.readCsv(csvReply)

        if df is not None and not df.empty:
                # Normalize column names
            df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]
                
                # Ensure we have a closetime column
            if 'closetime' not in df.columns:
                print("⚠️ No 'closetime' column - cannot identify closed positions")
                return pd.DataFrame()  # Return empty DataFrame
                
                # Convert to datetime and filter out open positions (NaT)
            df['closetime'] = pd.to_datetime(df['closetime'], errors='coerce')
            df = df[df['closetime'].notna()]  # Keep only rows with actual close times
                
            print(f"Found {len(df)} truly closed positions")
            return df
        
        return pd.DataFrame()  # Return empty DataFrame if no data


    def Get_closed_pl_today(self, timezone_offset: int = 3) -> float:
        """
        Returns the net profit/loss for trades closed today only, excluding deposits.
        Args:
            timezone_offset: Hours to adjust server time to local time
        Returns:
            float: Today's closed P/L (0 if no trades closed today)
        """
        df = self.Get_all_closed_positions()
        
        if df.empty:
            print("ℹ️ No closed positions found at all")
            return 0.0
        
        # Apply timezone adjustment
        df['closetime'] = df['closetime'] + pd.Timedelta(hours=timezone_offset)
        
        # Filter for today
        today = datetime.now().date()
        today_trades = df[df['closetime'].dt.date == today]
        
        if today_trades.empty:
            print(f"ℹ️ No trades closed today (current date: {today})")
            return 0.0
        
        # EXCLUDE DEPOSITS (where symbol is NaN and profit is positive)
        today_trades = today_trades[~((today_trades['symbol'].isna()) & (today_trades['profit'] > 0))]
        
        print(f"✔️ Found {len(today_trades)} trades closed today (excluding deposits):")
        print(today_trades[['ticket', 'symbol', 'closetime', 'profit']])
        
        return round(today_trades['profit'].sum(), 2)

    def readCsv(self, inputCsvString):
        try:
            return pd.read_csv(StringIO(inputCsvString))        
        except Exception as e:
            print(f"An error occurred: {e}")
            return None

    def send_command(self, command: TradingCommands, arguments: str = ''):
        msg = "{}^{}".format(command.value, arguments)
        self.socket.send_string(str(msg))
        reply = self.socket.recv_string()
        return reply
    
 