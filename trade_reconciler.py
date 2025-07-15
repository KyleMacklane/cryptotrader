import csv
import os
from datetime import datetime

class TransactionLogger:
    def __init__(self, csv_file="trade_history.csv"):
        self.csv_file = csv_file
        self.fieldnames = [
            "timestamp", "user_id", "tx_type", "amount", 
            "status", "tx_hash", "related_user", "notes"
        ]
    
    def log_trade(self, user_id: str, tx_type: str, amount: float, 
         tx_hash: str = "", related_user: str = "", notes: str = ""):
        """Log a trade transaction"""
        # Create file if not exists
        file_exists = os.path.isfile(self.csv_file)
        
        with open(self.csv_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            
            if not file_exists:
                writer.writeheader()
                
            writer.writerow({
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": user_id,
                "tx_type": tx_type,
                "amount": amount,
                "status": "PENDING",
                "tx_hash": tx_hash,
                "related_user": related_user,
                "notes": notes
            })
    
    def update_status(self, tx_hash: str, status: str, notes: str = ""):
        """Update transaction status"""
        transactions = []
        updated = False
        
        # Read all transactions
        with open(self.csv_file, "r") as f:
            reader = csv.DictReader(f)
            transactions = list(reader)
        
        # Update matching transaction
        for tx in transactions:
            if tx["tx_hash"] == tx_hash:
                tx["status"] = status
                tx["notes"] = notes
                updated = True
                break
        
        # Save back if updated
        if updated:
            with open(self.csv_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.fieldnames)
                writer.writeheader()
                writer.writerows(transactions)
            return True
        return False
    
    def reconcile_user(self, user_id: str):
        """Reconcile all transactions for a user"""
        user_transactions = []
        total_balance = 0.0
        
        # Read all transactions
        with open(self.csv_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["user_id"] == user_id and row["status"] == "COMPLETED":
                    user_transactions.append(row)
                    
                    # Calculate balance impact
                    if row["tx_type"] in ["DEPOSIT", "REFERRAL"]:
                        total_balance += float(row["amount"])
                    elif row["tx_type"] in ["WITHDRAWAL", "FEE"]:
                        total_balance -= float(row["amount"])
        
        return {
            "transactions": user_transactions,
            "calculated_balance": total_balance
        }
    
    def full_reconciliation(self):
        """Reconcile all accounts"""
        accounts = {}
        
        # Read all transactions
        with open(self.csv_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["status"] != "COMPLETED":
                    continue
                    
                user_id = row["user_id"]
                amount = float(row["amount"])
                
                if user_id not in accounts:
                    accounts[user_id] = 0.0
                
                # Calculate balance impact
                if row["tx_type"] in ["DEPOSIT", "REFERRAL"]:
                    accounts[user_id] += amount
                elif row["tx_type"] in ["WITHDRAWAL", "FEE"]:
                    accounts[user_id] -= amount
        
        return accounts