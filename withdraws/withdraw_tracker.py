from datetime import datetime, timedelta

import csv

MAX_WITHDRAWALS_PER_MONTH = 1
WITHDRAWAL_COOLDOWN = timedelta(days=30)
# MIN_DEPOSIT = 100
# MIN_WITHDRAWAL = 50

class WithdrawalTracker:
    def __init__(self, tracker_file="data/withdrawals.csv"):
        self.tracker_file = tracker_file
        self.fieldnames = ["user_id", "last_withdrawal_date", "withdrawals_this_month"]
        
    def _load_data(self):
        try:
            with open(self.tracker_file, "r") as f:
                return list(csv.DictReader(f))
        except FileNotFoundError:
            return []
        
    def can_withdraw(self, user_id):
        data = self._load_data()
        user_data = next((item for item in data if item["user_id"] == str(user_id)), None)
        
        if not user_data:
            return True
            
        last_date = datetime.strptime(user_data["last_withdrawal_date"], "%Y-%m-%d").date()
        withdrawals_count = int(user_data["withdrawals_this_month"])
        
        return (datetime.now().date() - last_date) >= WITHDRAWAL_COOLDOWN and withdrawals_count < MAX_WITHDRAWALS_PER_MONTH
    
    def record_withdrawal(self, user_id):
        data = self._load_data()
        user_data = next((item for item in data if item["user_id"] == str(user_id)), None)
        
        today = datetime.now().date()
        if user_data:
            last_date = datetime.strptime(user_data["last_withdrawal_date"], "%Y-%m-%d").date()
            if (today - last_date).days >= 30:
                user_data["withdrawals_this_month"] = "1"
            else:
                user_data["withdrawals_this_month"] = str(int(user_data["withdrawals_this_month"]) + 1)
            user_data["last_withdrawal_date"] = today.strftime("%Y-%m-%d")
        else:
            data.append({
                "user_id": str(user_id),
                "last_withdrawal_date": today.strftime("%Y-%m-%d"),
                "withdrawals_this_month": "1"
            })
            
        with open(self.tracker_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writeheader()
            writer.writerows(data)   