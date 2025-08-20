async def trading_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Generate and send trading statistics based on closed trades.
    Handles both CSV file and MT4 API as data sources.
    """
    try:
        # Get trades data from available sources
        trades = await get_trades_data()
        
        # Validate we have trades data
        if trades is None or trades.empty:
            await send_no_trades_message(update)
            return
        
        # Process and analyze the trades data
        msg = await generate_stats_message(trades)
        
        # Send the message
        await send_stats_message(update, msg)
        
    except Exception as e:
        logger.error(f"Failed to generate trading stats: {e}", exc_info=True)
        await send_error_message(update, "Failed to generate trading statistics.")

async def get_trades_data():
    """
    Retrieve trades data from CSV or fall back to MT4 API.
    Returns a DataFrame with trades or None if no data available.
    """
    csv_file = "trades_log.csv"
    
    # Try to get data from CSV first
    trades = await get_trades_from_csv(csv_file)
    if trades is not None:
        return trades
    
    # Fall back to MT4 if CSV is not available or empty
    return await get_trades_from_mt4()

async def get_trades_from_csv(csv_file):
    """
    Attempt to load trades data from CSV file.
    Returns DataFrame if successful, None otherwise.
    """
    if not (os.path.exists(csv_file) and os.path.getsize(csv_file) > 0):
        return None
    
    try:
        trades = pd.read_csv(csv_file)
        # Debug: Check date parsing
        print("Original closetime values from CSV:")
        print(trades['closetime'].head().tolist())

        trades['closetime'] = parse_mixed_dates(trades['closetime'])
        print("After parsing closetime values:")
        print(trades['closetime'].head().tolist())
        print("Date parts only:")
        print(trades['closetime'].dt.date.head().tolist())

        logger.info(f"Loaded {len(trades)} trades from {csv_file}")
        
        if trades.empty:
            logger.warning("CSV file is empty")
            return None
            
        # Standardize column names
        trades = standardize_column_names(trades)
        return trades
        
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as e:
        logger.warning(f"Error reading CSV file: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error reading CSV: {e}")
        return None

def standardize_column_names(trades):
    """
    Standardize column names in the trades DataFrame.
    """
    # Define expected columns in order
    expected_columns = [
        'ticket', 'symbol', 'position_type', 'openprice', 'closeprice',
        'profit', 'opentime', 'closetime', 'comment'
    ]
    
    # If we have no named columns or they're all unnamed, assign names
    if all(col.startswith('Unnamed:') or col.isdigit() for col in trades.columns):
        rename_dict = {}
        for i, col in enumerate(trades.columns):
            if i < len(expected_columns):
                rename_dict[col] = expected_columns[i]
        trades = trades.rename(columns=rename_dict)
        logger.info(f"Renamed columns: {list(trades.columns)}")
    
    # Handle case where we have some but not all expected columns
    elif not all(col in trades.columns for col in ['ticket', 'symbol', 'profit', 'closetime']):
        # Map by position for critical columns
        column_mapping = {}
        if len(trades.columns) >= 1 and 'ticket' not in trades.columns:
            column_mapping[trades.columns[0]] = 'ticket'
        if len(trades.columns) >= 2 and 'symbol' not in trades.columns:
            column_mapping[trades.columns[1]] = 'symbol'
        if len(trades.columns) >= 3 and 'position_type' not in trades.columns:
            column_mapping[trades.columns[2]] = 'position_type'
        if len(trades.columns) >= 6 and 'profit' not in trades.columns:
            column_mapping[trades.columns[5]] = 'profit'
        if len(trades.columns) >= 8 and 'closetime' not in trades.columns:
            column_mapping[trades.columns[7]] = 'closetime'
            
        if column_mapping:
            trades = trades.rename(columns=column_mapping)
            logger.info(f"Mapped columns: {list(trades.columns)}")
    
    return trades

async def get_trades_from_mt4():
    """
    Retrieve trades data from MT4 API.
    Returns DataFrame if successful, None otherwise.
    """
    try:
        mt4 = EACommunicator_API()
        if not mt4.Connect():
            logger.error("Failed to connect to MT4")
            return None
            
        trades = mt4.Get_all_closed_positions()
        if trades is None:
            logger.error("MT4 returned no trades data")
            return None
            
        # Ensure we have a DataFrame
        if not isinstance(trades, pd.DataFrame):
            logger.error(f"MT4 returned unexpected data type: {type(trades)}")
            return None
            
        logger.info(f"Retrieved {len(trades)} trades from MT4")
        return trades
        
    except Exception as e:
        logger.error(f"Error retrieving data from MT4: {e}")
        return None
    finally:
        # Clean up MT4 connection
        if 'mt4' in locals():
            try:
                mt4.Disconnect()
            except:
                pass

    # Handle mixed date formats in closetime and opentime
def parse_mixed_dates(date_series):
        # Parse as timezone-naive directly
    for fmt in ['%Y-%m-%d', '%Y.%m.%d']:
        try:
            return pd.to_datetime(date_series, format=fmt, errors='raise',utc=False)
        except:
            continue
        
        # Fallback - parse and then remove timezone to prevent date shifting
    result = pd.to_datetime(date_series, errors='coerce')
    if result.dt.tz is not None:
        result = result.dt.tz_convert(None)
    return result

def validate_and_clean_trades(trades):
    """
    Validate trades data and clean it for analysis.
    """

    
    # Convert date columns with proper format handling
    trades['closetime'] = parse_mixed_dates(trades['closetime'])
    trades['opentime'] = parse_mixed_dates(trades['opentime'])

        # Debug: Check what dates we actually have
    print(f"DEBUG: closetime range - {trades['closetime'].min()} to {trades['closetime'].max()}")
    print(f"DEBUG: closetime dates - {trades['closetime'].dt.date.unique()[:10]}") 
    
    trades['profit'] = pd.to_numeric(trades['profit'], errors='coerce')
    
    # Drop rows with invalid critical data
    initial_count = len(trades)
    trades = trades[trades['closetime'].notna()]
    trades = trades[trades['profit'].notna()]
    
    if len(trades) < initial_count:
        logger.info(f"Filtered out {initial_count - len(trades)} trades with invalid data")
    
    # Only include valid trading activity
    valid_trades = trades[
        trades['symbol'].notna() & 
        (trades['symbol'].str.strip() != "") & 
        (trades['position_type'].isin(["buy", "sell"]))
    ]
    
    if len(valid_trades) < len(trades):
        logger.info(f"Filtered out {len(trades) - len(valid_trades)} non-trading records")
    
    return valid_trades

def calculate_date_ranges():
    """
    Calculate common date ranges for statistics.
    Returns a dictionary of date ranges.
    """
    now = datetime.now()
    today = now.date()
    start_of_week = (today - timedelta(days=today.weekday()))
    start_of_month = today.replace(day=1) #This gives us the first day of the current month, regardless of what today's day is.
    last_day_of_prev_month = start_of_month - timedelta(days=1)
    last_month_start = last_day_of_prev_month.replace(day=1)  # First day of previous month
    last_month_end = last_day_of_prev_month  # Last day of previous month        

    past_3_months = today - relativedelta(months=3)
    past_6_months = today - relativedelta(months=6)
    past_1_year = today - relativedelta(years=1)
    
    return {
        'today': today,
        'start_of_week': start_of_week,
        'start_of_month': start_of_month,
        'last_month_start': last_month_start,
        'last_month_end': last_month_end,
        'past_3_months': past_3_months,
        'past_6_months': past_6_months,
        'past_1_year': past_1_year
    }

def filter_trades_by_date(trades, date_ranges):
    """
    Filter trades based on date ranges using date objects.
    """
    # Debug: Print the date ranges
    print(f"DEBUG: Date ranges - {date_ranges}")
    
    # Extract just the date part from closetime for comparison
    close_dates = trades['closetime'].dt.date
    
    # Convert all date ranges to date objects if they contain datetime objects
    date_ranges_date = {
        'today': date_ranges['today'].date() if isinstance(date_ranges['today'], datetime) else date_ranges['today'],
        'start_of_week': date_ranges['start_of_week'].date() if isinstance(date_ranges['start_of_week'], datetime) else date_ranges['start_of_week'],
        'start_of_month': date_ranges['start_of_month'].date() if isinstance(date_ranges['start_of_month'], datetime) else date_ranges['start_of_month'],
        'last_month_start': date_ranges['last_month_start'].date() if isinstance(date_ranges['last_month_start'], datetime) else date_ranges['last_month_start'],
        'last_month_end': date_ranges['last_month_end'].date() if isinstance(date_ranges['last_month_end'], datetime) else date_ranges['last_month_end'],
        'past_3_months': date_ranges['past_3_months'].date() if isinstance(date_ranges['past_3_months'], datetime) else date_ranges['past_3_months'],
        'past_6_months': date_ranges['past_6_months'].date() if isinstance(date_ranges['past_6_months'], datetime) else date_ranges['past_6_months'],
        'past_1_year': date_ranges['past_1_year'].date() if isinstance(date_ranges['past_1_year'], datetime) else date_ranges['past_1_year']
    }
    
    # Filter trades by date ranges using date objects
    filtered = {
        'daily_trades': trades[close_dates == date_ranges_date['today']],
        'weekly_trades': trades[close_dates >= date_ranges_date['start_of_week']],
        'monthly_trades': trades[
            (close_dates >= date_ranges_date['start_of_month']) &
            (close_dates <= date_ranges_date['today'])
        ],
        'last_month_trades': trades[
            (close_dates >= date_ranges_date['last_month_start']) &
            (close_dates <= date_ranges_date['last_month_end'])
        ],
        'last_3_months_trades': trades[close_dates >= date_ranges_date['past_3_months']],
        'last_6_months_trades': trades[close_dates >= date_ranges_date['past_6_months']],
        'last_year_trades': trades[close_dates >= date_ranges_date['past_1_year']]
    }
    
    # Debug: Print counts for each filtered group
    for key, df in filtered.items():
        print(f"DEBUG: {key} - {len(df)} trades")
        if not df.empty:
            print(f"DEBUG: {key} dates - {df['closetime'].dt.date.min()} to {df['closetime'].dt.date.max()}")
    
    return filtered

def calculate_stats(df, label):
    """
    Calculate statistics for a DataFrame of trades.
    """
    if df.empty:
        return f"*{label}*\n• No trades found\n"
    
    total_profit = df['profit'].sum()
    successful = df[df['profit'] > 0].shape[0]
    unsuccessful = df[df['profit'] <= 0].shape[0]
    total_trades = successful + unsuccessful
    win_rate = (successful / total_trades * 100) if total_trades > 0 else 0
    
    return (
        f"*{label}*\n"
        f"• Total Profit: `{total_profit/100:.2f}%`\n"
        f"• ✅ Successful Trades: {successful}\n"
        f"• ❌ Unsuccessful Trades: {unsuccessful}\n"
        f"• 📊 Win Rate: {win_rate:.1f}%\n"
    )

async def generate_stats_message(trades):
    """
    Generate the statistics message from trades data.
    """
    # Validate and clean the data
    valid_trades = validate_and_clean_trades(trades)
    
    if valid_trades.empty:
        return "No valid trading data available for analysis."
    
    # Calculate date ranges
    date_ranges = calculate_date_ranges()
    
    # Filter trades by date ranges
    filtered_trades = filter_trades_by_date(valid_trades, date_ranges)
    
    # Generate statistics message
    msg = (
        "📊 *Trading Statistics*\n\n"
        + calculate_stats(filtered_trades['daily_trades'], "📅 Today")
        + "\n"
        + calculate_stats(filtered_trades['weekly_trades'], "🗓️ This Week")
        + "\n"
        + calculate_stats(filtered_trades['monthly_trades'], "📆 This Month")
        + "\n"
        + calculate_stats(filtered_trades['last_month_trades'], "📉 Last Month")
        # + "\n"
        # + calculate_stats(filtered_trades['last_3_months_trades'], "🪻 Past 3 Months")
        # + "\n"
        # + calculate_stats(filtered_trades['last_6_months_trades'], "🌼 Past 6 Months")
        # + "\n"
        # + calculate_stats(filtered_trades['last_year_trades'], "📈 Past 1 Year")
    )
    
    return msg

async def send_no_trades_message(update):
    """Send message when no trades are found."""
    message = "❌ No closed trades found."
    await send_message(update, message)

async def send_error_message(update, message):
    """Send error message."""
    await send_message(update, f"⚠️ {message}")

async def send_stats_message(update, msg):
    """Send statistics message."""
    await send_message(update, msg, parse_mode='Markdown')

async def send_message(update, message, parse_mode=None):
    """Send message to the appropriate chat."""
    try:
        if update.message:
            await update.message.reply_text(message, parse_mode=parse_mode)
        elif update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(message, parse_mode=parse_mode)
        else:
            logger.warning("No message or callback_query found in update")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

