# Add this test function to debug the issue
def test_date_filtering():
    """Test if July dates are correctly identified as last month"""
    from datetime import date
    import pandas as pd
    
    # Create test data matching your CSV
    test_dates = [
        '2025-07-31', '2025-07-31', '2025-07-31', 
        '2025-07-31', '2025-07-31', '2025-08-10',
        '2025-08-10', '2025-08-07', '2025-08-07'
    ]
    
    test_df = pd.DataFrame({
        'closetime': pd.to_datetime(test_dates),
        'profit': [0.07, 12.43, 13.65, 7.74, 5.96, 10, 15, 8, 12]
    })
    
    # Simulate August 2025 as current date
    august_2025 = date(2025, 8, 15)
    
    # Calculate what should be last month (July 2025)
    last_month_start = date(2025, 7, 1)
    last_month_end = date(2025, 7, 31)
    
    print(f"Test - Current date: {august_2025}")
    print(f"Test - Last month range: {last_month_start} to {last_month_end}")
    print(f"Test - Dates in data: {test_df['closetime'].dt.date.unique()}")
    
    # Filter for last month
    last_month_trades = test_df[
        (test_df['closetime'].dt.date >= last_month_start) &
        (test_df['closetime'].dt.date <= last_month_end)
    ]
    
    print(f"Test - Last month trades found: {len(last_month_trades)}")
    return len(last_month_trades)

# Call this test function to see what's happening
test_result = test_date_filtering()
print(f"Test result: {test_result} trades should be found for last month")