import csv
import os
from datetime import datetime
from filelock import FileLock

class TransactionLogger:
    def __init__(self, file_name="transactions.csv"):
        self.file_name = file_name
        self.lock = FileLock(f"{file_name}.lock")

        # Create file with headers if not exists
        if not os.path.exists(self.file_name):
            with open(self.file_name, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["telegram_id", "type", "amount", "timestamp"])

    def log(self, telegram_id, tx_type, amount):
        with self.lock:
            with open(self.file_name, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    telegram_id,
                    tx_type,
                    f"{amount:.2f}",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ])
