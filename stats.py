    def _is_user_pending(self, telegram_id):
        """Check if user is in pending list"""
        pending_file = "pending_users.csv"
        try:
            if not os.path.exists(pending_file):
                return False
                
            with open(pending_file, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["telegram_id"] == str(telegram_id) and row["status"] == "pending":
                        return True
            return False
        except Exception as e:
            logger.error(f"Error checking pending user: {e}")
            return False