import csv
import os
import logging
from datetime import datetime
from filelock import FileLock  
from trade_reconciler import TransactionLogger
tx_logger = TransactionLogger()
from mt5.mt5service import MT5Service
import json
from mt5.EACommunicator_API import EACommunicator_API

MT5_CREDENTIALS = {
    'login':  210708328,
    'server': "Exness-MT5Trial9",
    'password': "Unclehard2025@"
}


logger = logging.getLogger(__name__)
class AccountManager:
    def __init__(self, csv_file="/data/accounts.csv"):
        self.csv_file = csv_file
        self.lock = FileLock(f"{csv_file}.lock")
        self.fieldnames = [
            "telegram_id", "server", "user_id", "balance", 
            "referral_id", "referrals", "referral_earnings","total_withdrawals","total_deposits",
            "first_deposit", "first_deposit_date", "first_deposit_amount", "last_interest_date","total_interest", "referrer_id", "locked",
            "mt5_allocation", "last_profit_date", "profit_share_rate", "last_profit_share"
    ]
        self.ea = EACommunicator_API()
        self.ea.Connect()

    def _load_accounts(self):
        try:
            with self.lock:
                if not os.path.exists(self.csv_file):
                    with open(self.csv_file, "w", newline="") as f:
                        writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                        writer.writeheader()             
                        return []
                
                with open(self.csv_file, "r") as f:
                    return list(csv.DictReader(f))
        except Exception as e:
            logger.error(f"Error loading accounts: {e}")
            return []

    def _save_accounts(self, accounts):
        try:
            with self.lock:
                with open(self.csv_file, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                    writer.writeheader()
                    writer.writerows(accounts)
            return True
        except Exception as e:
            logger.error(f"Error saving accounts: {e}")
            return False

    def get_account_info(self, telegram_id):
        accounts = self._load_accounts()
        for acc in accounts:
            if acc["telegram_id"] == str(telegram_id):
                return acc
        return None

    def add_user_if_not_exists(self, telegram_id, server, user_id,referral_id=None):
        accounts = self._load_accounts()
        if any(acc["telegram_id"] == str(telegram_id) for acc in accounts):
            return
        
        #create a new account
        new_account = {
            "telegram_id": str(telegram_id),
            "server": server,
            "user_id": user_id,
            "balance": "0.00",
            "total_withdrawals": "0.00",
            "referral_id": self._generate_referral_id(telegram_id),
            "referrals": "0",
            "referral_earnings": "0.00",
            "first_deposit": "0",
            "first_deposit_date": "",
            "first_deposit_amount": "0.00",
            "total_deposits": "0.00",
            "last_interest_date": datetime.now().strftime("%Y-%m-%d"),
            "total_interest": "0.00",
            "referrer_id": referral_id or "",
            "locked": "0.00",
            "mt5_allocation": "0.00",
            "last_profit_date": "",
            "profit_share_rate": "0.15",
            "last_profit_share": ""
        }
     
        # Add referrer if provided
        if referral_id:
    # Convert referral_id to Telegram ID
            referrer_telegram_id = self._get_telegram_id_from_referral_id(referral_id)
            if referrer_telegram_id:
                new_account["referrer_id"] = referrer_telegram_id
                self._add_referral(referrer_telegram_id)
        
        accounts.append(new_account)
        self._save_accounts(accounts)

    def get_floating_pl(self):
        """Get current floating P/L from open positions"""
        try:
            open_positions = self.ea.Get_all_open_positions()
            if open_positions is not None and not open_positions.empty:
                return open_positions['profit'].sum()
            return 0.0
        except Exception as e:
            logger.error(f"Error getting floating P/L: {e}")
            return 0.0
        
    def record_trade(self, trade_data):
        """Record a trade in the history"""
        fieldnames = ["timestamp", "ticket", "symbol", "type", "volume", 
                     "open_price", "close_price", "profit", "swap", "commission"]
        
        try:
            with open(self.trades_file, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if f.tell() == 0:
                    writer.writeheader()
                writer.writerow(trade_data)
            return True
        except Exception as e:
            logger.error(f"Error recording trade: {e}")
            return False
   
    def get_trades_since(self, since_timestamp):
        """Get all trades since given timestamp"""
        try:
            trades = []
            with open(self.trades_file, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if datetime.fromisoformat(row["timestamp"]) > since_timestamp:
                        trades.append(row)
            return trades
        except Exception as e:
            logger.error(f"Error reading trades: {e}")
            return []
        
    def get_last_distribution_time(self):
        """Get timestamp of last profit distribution"""
        try:
            with open("distributions.csv", "r") as f:
                reader = csv.DictReader(f)
                last = list(reader)[-1]
                return datetime.fromisoformat(last["timestamp"])
        except (FileNotFoundError, IndexError):
            return datetime.min         

    def record_distribution_time(self):
        """Record when profits were last distributed"""
        try:
            with open("distributions.csv", "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["timestamp"])
                if f.tell() == 0:
                    writer.writeheader()
                writer.writerow({"timestamp": datetime.now().isoformat()})
            return True
        except Exception as e:
            logger.error(f"Error recording distribution time: {e}")
            return False
                                
    def get_closed_pl(self):
        """Get realized P/L from closed positions"""
        try:
            closed_positions = self.ea.Get_all_closed_positions()
            if closed_positions is not None and not closed_positions.empty:
                return closed_positions['profit'].sum()
            return 0.0
        except Exception as e:
            logger.error(f"Error getting closed P/L: {e}")
            return 0.0    

    @staticmethod
    def get_processed_trades():
        try:
            with open('processed_trades.json', 'r') as f:
                return set(json.load(f).get('processed_tickets', []))
        except (FileNotFoundError, json.JSONDecodeError):
            return set()
        
    @staticmethod
    def save_processed_trades(trade_ids):
        data = {'processed_tickets': list(trade_ids)}
        with open('processed_trades.json', 'w') as f:
            json.dump(data, f)

    def get_current_equity(self, telegram_id):
        """Calculate current equity (balance + floating P/L)"""
        account = self.get_account_info(telegram_id)
        if not account:
            return 0.0
            
        balance = float(account.get('balance', 0))
        return balance + self.get_floating_pl()
    
    
    
    def process_deposit(self, telegram_id: str, amount: float) -> bool:
        """Handle new deposits"""
        accounts = self._load_accounts()
        for acc in accounts:
            if acc["telegram_id"] == str(telegram_id):
                # Apply 10% fee
                net_amount = amount * 0.90
                
                # Update balance
                current = float(acc["balance"])
                acc["balance"] = f"{current + net_amount:.2f}"
                

                
                # First deposit handling
                if acc["first_deposit"] == "0":
                    acc["first_deposit"] = "1"
                    acc["first_deposit_amount"] = f"{amount:.2f}"  
                    acc["first_deposit_date"] = datetime.now().strftime("%Y-%m-%d")
                    # current_deposits = float(acc.get("total_deposits") or 0)
                    # acc["total_deposits"] = f"{net_amount:.2f}"
                
                
                current_deposits = float(acc.get("total_deposits")or 0)
                acc["total_deposits"] = f"{current_deposits + net_amount:.2f}"
                
                saved = self._save_accounts(accounts)
                if not saved:
                    print(f"❌ Failed to save updated account for {telegram_id}")
                return saved
            
        return False


    def distribute_profits(self, current_mt5_balance: float) -> bool:
        
        accounts = self._load_accounts()
        total_deposits = self.get_total_deposits()
        total_withdrawals = self.get_total_withdrawals()
        
        # Calculate net profit pool
        balance1 = current_mt5_balance - total_deposits - total_withdrawals
        
        updated = False
        for acc in accounts:
            user_deposits = float(acc.get("total_deposits", 0))
            user_withdrawals = float(acc.get("total_withdrawals", 0))
            
            if user_deposits > 0:  # Only users who deposited
                # Calculate individual profit share
                individual_profit = (user_deposits / total_deposits) * balance1
                
                # Calculate new balance
                if (user_deposits - user_withdrawals) > 0:
                    new_balance = individual_profit + user_deposits - user_withdrawals
                else:
                    new_balance = individual_profit - abs(user_deposits - user_withdrawals)
                
                # Update account
                acc["balance"] = f"{new_balance:.2f}"
                
                # Track profits
                if individual_profit > 0:
                    current_interest = float(acc.get("total_interest", 0))
                    acc["total_interest"] = f"{current_interest + individual_profit:.2f}"
                
                acc["last_profit_date"] = datetime.now().strftime("%Y-%m-%d")
                updated = True
        
        if updated:
            return self._save_accounts(accounts)
        return False

    def _generate_referral_id(self, telegram_id):
            return "REF" + str(telegram_id)[-6:] + datetime.now().strftime("%m%d")    

    def _get_telegram_id_from_referral_id(self, referral_id: str) -> str:
        accounts = self._load_accounts()
        for acc in accounts:
            if acc.get("referral_id") == referral_id:
                return acc["telegram_id"]
        return None


    def _add_referral(self, referrer_id):
        accounts = self._load_accounts()
        for acc in accounts:
            if acc["telegram_id"] == str(referrer_id):
                # Update referral count
                current_refs = int(acc.get("referrals", "0"))
                acc["referrals"] = str(current_refs + 1)
                
                # Mark if first referral
                if current_refs == 0:
                    acc["first_referral"] = "1"
                
                self._save_accounts(accounts)
                return True
        return False

    def add_referral_earning(self, referrer_id, amount):
        accounts = self._load_accounts()
        for acc in accounts:
            if acc["telegram_id"] == str(referrer_id):
                # Calculate 10% bonus
                bonus = amount * 0.10
                tx_logger.log_trade(
                    user_id=str(referrer_id),
                    tx_type="REFERRAL",
                    amount=bonus,
                    related_user=str(referrer_id),
                    notes=f"Bonus from referral deposit"
                )
                # Update referral earnings
                current_earnings = float(acc.get("referral_earnings", "0"))
                acc["referral_earnings"] = str(round(current_earnings + bonus, 2))
                # Update main balance
                current_balance = float(acc.get("balance", "0"))
                acc["balance"] = str(round(current_balance + bonus, 2))
                
                self._save_accounts(accounts)
                return True
        return False
    

    def get_referral_info(self, telegram_id):
        account = self.get_account_info(telegram_id)
        if not account:
            return None
        
        return {
            "referral_id": account.get("referral_id", ""),
            "referral_count": account.get("referrals", "0"),
            "referral_earnings": account.get("referral_earnings", "0.00")
        }
    
    def calculate_user_balance(self, telegram_id):
        """Calculate balance using MQL-style formula"""
        account = self.get_account_info(telegram_id)
        if not account:
            return 0.0
            
        total_deposits = float(account.get("total_deposits", 0))
        user_withdrawals = float(account.get("total_withdrawals", 0))
        
        # Get system totals
        sys_total_deposits = self.get_total_deposits()
        sys_total_withdrawals = self.get_total_withdrawals()
        current_mt5_balance = MT5Service.get_balance(telegram_id)
        
        # Calculate net pool
        balance1 = current_mt5_balance - sys_total_deposits - sys_total_withdrawals
        
        # Individual share
        if sys_total_deposits > 0:
            individual_profit = (total_deposits / sys_total_deposits) * balance1
        else:
            individual_profit = 0
            
        # Final balance
        if (total_deposits - user_withdrawals) > 0:
            return individual_profit + total_deposits - user_withdrawals
        else:
            return individual_profit - abs(total_deposits - user_withdrawals)
    
    def update_balance(self, telegram_id, amount, apply_fee=False):
        try:
            accounts = self._load_accounts()
            for acc in accounts:
                if acc["telegram_id"] == str(telegram_id):
                    current = float(acc["balance"])

                    # Apply 10% deduction if requested
                    net_amount = amount * 0.90 if apply_fee else amount
                    new_balance = current + net_amount


                    if new_balance < 0:
                        logger.warning(f"Insufficient balance for {telegram_id}")
                        return False
                    

                    # Check and set first deposit details 
                    if float(acc.get("first_deposit", "0")) == 0 and amount > 0:
                        acc["first_deposit"] = f"{amount:.2f}"
                        acc["first_deposit_amount"] = f"{amount:.2f}"
                        acc["first_deposit_date"] = datetime.utcnow().strftime("%Y-%m-%d")

                     # ✅ Update total_deposits if it's a deposit
                    # if amount > 0:
                    #     current_deposits = float(acc.get("total_deposits") or 0)
                    #     acc["total_deposits"] = f"{current_deposits + net_amount:.2f}"

                    # Preserve all existing fields while updating balance
                    updated_account = {
                        **acc,  # Keeps all existing fields
                        "balance": f"{new_balance:.2f}"
                    }
                    accounts[accounts.index(acc)] = updated_account
                    return self._save_accounts(accounts)

            logger.warning(f"Account {telegram_id} not found")
            return False

        except Exception as e:
            logger.error(f"Error updating balance: {e}")
            return False

    
    def update_profit_share(self, telegram_id: str, amount: float) -> bool:
        """Credit profit share to user"""
        accounts = self._load_accounts()
        for acc in accounts:
            if acc["telegram_id"] == str(telegram_id):
                # Update balance
                current = float(acc["balance"])
                acc["balance"] = f"{current + amount:.2f}"
                
                # Update tracking fields
                acc["last_profit_date"] = datetime.now().strftime("%Y-%m-%d")
                current_interest = float(acc.get("total_interest", 0))
                acc["total_interest"] = f"{current_interest + amount:.2f}"
                
                return self._save_accounts(accounts)
        return False

  
    def decrease_balance(self, telegram_id, amount):
        try:
            accounts = self._load_accounts()
            for acc in accounts:
                if acc["telegram_id"] == str(telegram_id):
                    current = float(acc["balance"])
                    if current < amount:
                        logger.warning(f"Insufficient balance for {telegram_id}")
                        return False
                    acc["balance"] = f"{current - amount:.2f}"
                    return self._save_accounts(accounts)
            return False
        except Exception as e:
            logger.error(f"Error decreasing balance: {e}")
            return False
      
    def set_balance(self, telegram_id, new_balance):
        accounts = self._load_accounts()
        for acc in accounts:
            if acc["telegram_id"] == str(telegram_id):
                acc["balance"] = f"{new_balance:.2f}"
                self._save_accounts(accounts)
                return True
        return False

    def get_balance(self, telegram_id):
        account = self.get_account_info(telegram_id)
        return float(account["balance"]) if account else 0.0
    
    def get_total_deposits(self):
        accounts = self._load_accounts()
        return sum(float(acc.get("total_deposits", 0)) for acc in accounts)

    def get_total_withdrawals(self):
        accounts = self._load_accounts()
        return sum(float(acc.get("total_withdrawals", 0)) for acc in accounts)

    def update_total_withdrawals(self, telegram_id, amount):
        try:
            accounts = self._load_accounts()
            for acc in accounts:
                if acc["telegram_id"] == str(telegram_id):
                    current_withdrawals = float(acc.get("total_withdrawals", 0))
                    
                    # Preserve all existing fields while updating withdrawals
                    updated_account = {
                        **acc,  # Keep all existing fields
                        "total_withdrawals": f"{current_withdrawals + amount:.2f}"
                    }
                    accounts[accounts.index(acc)] = updated_account
                    return self._save_accounts(accounts)
            return False
        except Exception as e:
            logger.error(f"Error updating total withdrawals: {e}")
            return False
    
    def lock_funds(self, user_id: str, amount: float):
        accounts = self._load_accounts()
        for acc in accounts:
            if acc['telegram_id'] == user_id:
                if float(acc['balance']) >= amount:
                    acc['locked'] = str(float(acc.get('locked', 0)) + amount)
                    self._save_accounts(accounts)
                    return True
        return False
    def get_locked_funds(self, user_id: str) -> float:
        accounts = self._load_accounts()
        for acc in accounts:
            if acc['telegram_id'] == user_id:
                return float(acc.get('locked', 0))
        return 0.0
