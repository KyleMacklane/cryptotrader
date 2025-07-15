# account_manager.py
import csv
import os
import logging
from datetime import datetime
from filelock import FileLock  
from trade_reconciler import TransactionLogger
tx_logger = TransactionLogger()

logger = logging.getLogger(__name__)
class AccountManager:
    def __init__(self, csv_file="accounts.csv"):
        self.csv_file = csv_file
        self.lock = FileLock(f"{csv_file}.lock")
        self.fieldnames = [
            "telegram_id", "server", "user_id", "balance", 
            "referral_id", "referrals", "referral_earnings","total_withdrawals",
            "first_deposit", "referrer_id", "locked"
    ]

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
            "referrer_id": referral_id or "",
            "locked": "0.00"
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
    
    
    def update_balance(self, telegram_id, amount, apply_fee=False):
        try:
            accounts = self._load_accounts()
            for acc in accounts:
                if acc["telegram_id"] == str(telegram_id):
                    current = float(acc["balance"])

                    # Apply 5% deduction if requested
                    net_amount = amount * 0.95 if apply_fee else amount
                    new_balance = current + net_amount

                    if new_balance < 0:
                        logger.warning(f"Insufficient balance for {telegram_id}")
                        return False

                    # Preserve all existing fields while updating balance
                    updated_account = {
                        **acc,  # Keep all existing fields
                        "balance": f"{new_balance:.2f}"
                    }
                    accounts[accounts.index(acc)] = updated_account
                    return self._save_accounts(accounts)

            logger.warning(f"Account {telegram_id} not found")
            return False

        except Exception as e:
            logger.error(f"Error updating balance: {e}")
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
