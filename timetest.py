from datetime import datetime, timedelta

now = datetime.now()
today = now.date()
start_of_week = (today - timedelta(days=today.weekday()))
start_of_month = today.replace(day=1) #This gives us the first day of the current month, regardless of what today's day is.
last_month_end = start_of_month - timedelta(days=1) # We then subtract one day from that to get the last day of last month
last_month_start = last_month_end.replace(day=1) # And we replace that with  again to get the first day of last month
        
print(f"Today: {today}")
print(f"Start of Week: {start_of_week}")
print(f"Start of Month: {start_of_month}")
print(f"Last Month Start: {last_month_start}")
print(f"Last Month End: {last_month_end}")