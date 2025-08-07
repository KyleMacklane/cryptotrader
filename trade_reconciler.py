from argparse import Action
import csv
import os
import uuid
from datetime import datetime
import logging
import pandas as pd
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TransactionLogger:
    def __init__(self, csv_file="trade_history.csv"):
        self.csv_file = csv_file
        self.fieldnames = [
            "timestamp", "user_id", "tx_id", "tx_type", "amount", 
            "status","address", "related_user", "notes"
        ]
        self.ensure_csv_has_header()
    
    def ensure_csv_has_header(self):
        """Ensure the CSV file has correct headers. If missing, insert them."""
        if not os.path.exists(self.csv_file):
            return  # No file yet, nothing to fix

        with open(self.csv_file, "r+", newline="") as f:
            first_line = f.readline()
            # Check if the first line is a valid header (starts with 'timestamp')
            if not first_line.startswith("timestamp"):
                # Read the rest of the file
                rest = f.read()
                f.seek(0)
                f.write(",".join(self.fieldnames) + "\n" + first_line + rest)
                logger.warning("⚠️ Header was missing in CSV. Header has been inserted.")


    def log_trade(self, user_id: str, tx_type: str, amount: float, status="PENDING",address:str=None,
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
                "status": status,
                "address": address,
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

    def get_user_transactions(self, user_id: int, limit: int = 10, txn_type: str = None):
        """Get all transactions for a specific user"""
        try:
            df = pd.read_csv(self.csv_file)

            if 'user_id' not in df.columns:
                raise KeyError("'user_id' column not found in CSV")

            # Normalize types
            df['user_id'] = df['user_id'].astype(str)
            user_txns = df[df['user_id'] == str(user_id)].copy()  # <-- Prevent chained assignment

            if txn_type:
                user_txns = user_txns[user_txns['tx_type'].str.upper() == txn_type.upper()]

            
            if 'timestamp' in user_txns.columns:
                user_txns['timestamp'] = pd.to_datetime(user_txns['timestamp'], errors='coerce')
                user_txns['timestamp'] = user_txns['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')

            return user_txns[['timestamp', 'tx_type', 'amount', 'status','address']].sort_values('timestamp', ascending=False).head(limit)

        except Exception as e:
            logger.error(f"Error reading transactions: {e}")
            return pd.DataFrame()
