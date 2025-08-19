
from enum import Enum
import json
import zmq
import pandas as pd
from datetime import datetime, timedelta, time
from io import StringIO
import os

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

        print("response gotten")
        # print("RAW RESPONSE FROM EA:", csvReply)
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

            self._append_to_trades_log(df)

            return df
        
        return pd.DataFrame()  # Return empty DataFrame if no data

    def _append_to_trades_log(self, df: pd.DataFrame):
        """Append new trades to the trades_log.csv file, avoiding duplicates."""
        try:
            csv_file = "trades_log.csv"
            
            # Check if file exists and is not empty
            file_exists = os.path.exists(csv_file) and os.path.getsize(csv_file) > 0
            
            existing_trade_ids = set()
            
            if file_exists:
                try:
                    # Read existing data - use first column as ticket IDs
                    existing_df = pd.read_csv(csv_file)
                    if not existing_df.empty:
                        # Get the first column (ticket IDs)
                        ticket_column = existing_df.columns[0]
                        existing_trade_ids = set(existing_df[ticket_column].astype(str))
                        print(f"📋 Found {len(existing_trade_ids)} existing trades in log")
                    else:
                        print("⚠️ Existing trades file is empty")
                        file_exists = False
                except pd.errors.EmptyDataError:
                    print("⚠️ Trades file is empty - creating new file")
                    file_exists = False
                except Exception as e:
                    print(f"⚠️ Could not read existing trades file: {e}")
                    file_exists = False
            
            # Get the first column from incoming data (should be ticket IDs)
            if len(df.columns) > 0:
                ticket_column_name = df.columns[0]
                print(f"🎫 Using '{ticket_column_name}' as ticket identifier")
                
                # Filter out trades that already exist in the file
                if existing_trade_ids:
                    new_trades = df[~df[ticket_column_name].astype(str).isin(existing_trade_ids)]
                else:
                    new_trades = df
                
                if not new_trades.empty:
                    # Append to CSV (create file if it doesn't exist)
                    mode = 'a' if file_exists else 'w'
                    header = not file_exists  # Write header only if creating new file
                    
                    new_trades.to_csv(csv_file, mode=mode, header=header, index=False)
                    print(f"✅ Appended {len(new_trades)} new trades to {csv_file}")
                else:
                    print("ℹ️ No new trades to append to log file")
            else:
                print("❌ No columns in incoming data")
                
        except Exception as e:
            print(f"❌ Error writing to trades log: {e}")
            import traceback
            traceback.print_exc()

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
    
 