from argparse import Action
import csv
import os
import uuid
from datetime import datetime

class TransactionLogger:
    def __init__(self, csv_file="trade_history.csv"):
        self.csv_file = csv_file
        self.fieldnames = [
            "timestamp", "user_id", "tx_id", "tx_type", "amount", 
            "status", "related_user", "notes"
        ]
    
    def log_trade(self, user_id: str, tx_type: str, amount: float, 
                  related_user: str = "", notes: str = "",tx_id: str = None) -> str:
        """Log a trade transaction and return tx_id"""
        if tx_id is None:
            tx_id = str(uuid.uuid4())
            
        file_exists = os.path.isfile(self.csv_file)

        with open(self.csv_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            if not file_exists:
                writer.writeheader()
            
            writer.writerow({
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": user_id,
                "tx_id": tx_id,
                "tx_type": tx_type.upper(),
                "amount": f"{amount:.2f}",
                "status": "PENDING",
                
                "related_user": related_user,
                "notes": notes
            })
        
        return tx_id
    
    def update_status(self, tx_id: str, status: str, notes: str = "") -> bool:
        """Update transaction status by tx_id"""
        transactions = []
        updated = False

        with open(self.csv_file, "r") as f:
            reader = csv.DictReader(f)
            transactions = list(reader)

        for tx in transactions:
            if tx.get("tx_id") == tx_id:
                tx["status"] = status.upper()
                tx["notes"] = notes
               
                updated = True
                break

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

        with open(self.csv_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["user_id"] == user_id and row["status"].upper() == "COMPLETED":
                    user_transactions.append(row)

                    if row["tx_type"] in ["DEPOSIT", "REFERRAL"]:
                        total_balance += float(row["amount"])
                    elif row["tx_type"] in ["WITHDRAWAL", "FEE"]:
                        total_balance -= float(row["amount"])

        return {
            "transactions": user_transactions,
            "calculated_balance": total_balance
        }
    
    def full_reconciliation(self):
        """Reconcile all user balances"""
        accounts = {}

        with open(self.csv_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["status"].upper() != "COMPLETED":
                    continue

                user_id = row["user_id"]
                amount = float(row["amount"])

                if user_id not in accounts:
                    accounts[user_id] = 0.0

                if row["tx_type"] in ["DEPOSIT", "REFERRAL"]:
                    accounts[user_id] += amount
                elif row["tx_type"] in ["WITHDRAWAL", "FEE"]:
                    accounts[user_id] -= amount

        return accounts
