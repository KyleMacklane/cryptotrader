import MetaTrader5 as mt5
from datetime import datetime
import pytz

class MT5Service:
    def __init__(self, login, server, password):
        self.login = login
        self.server = server
        self.password = password
        
    def connect(self):
        if not mt5.initialize():
            raise ConnectionError(f"MT5 init failed: {mt5.last_error()}")
        if not mt5.login(self.login, self.password, self.server):
            raise ConnectionError(f"Login failed: {mt5.last_error()}")
        return True
    
    def get_balance(self):
        account_info = mt5.account_info()
        if account_info is None:
            raise ValueError(f"Failed to get balance: {mt5.last_error()}")
        return account_info.balance
    
    def shutdown(self):
        mt5.shutdown()
        
    def get_server_time(self):
        return datetime.now(pytz.timezone('EET'))  # MT5 server timezone