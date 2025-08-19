async def trading_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        csv_file = "trades_log.csv"
        trades = pd.DataFrame()


        if os.path.exists(csv_file) and os.path.getsize(csv_file) > 0:
            try:
                trades = pd.read_csv(csv_file)
                print(f"📊 Loaded {len(trades)} trades from {csv_file}")

                # If we got an empty dataframe but file exists, fall back to MT4
                if trades.empty:
                    print("⚠️ CSV file is empty - falling back to MT4")
                    raise ValueError("Empty CSV file")
                
                if len(trades.columns) > 0 and 'ticket' not in trades.columns:
                    # Try to identify which column is which based on position
                    column_mapping = {}
                    if len(trades.columns) >= 1:
                        column_mapping[trades.columns[0]] = 'ticket'
                    if len(trades.columns) >= 2:
                        column_mapping[trades.columns[1]] = 'symbol'
                    if len(trades.columns) >= 3:
                        column_mapping[trades.columns[2]] = 'position_type'
                    if len(trades.columns) >= 4:
                        column_mapping[trades.columns[3]] = 'openprice'
                    if len(trades.columns) >= 5:
                        column_mapping[trades.columns[4]] = 'closeprice'
                    if len(trades.columns) >= 6:
                        column_mapping[trades.columns[5]] = 'profit'
                    if len(trades.columns) >= 7:
                        column_mapping[trades.columns[6]] = 'opentime'
                    if len(trades.columns) >= 8:
                        column_mapping[trades.columns[7]] = 'closetime'

                    if len(trades.columns) >= 9:
                        column_mapping[trades.columns[8]] = 'comment'                            



                    trades = trades.rename(columns=column_mapping)
                    print(f"🔧 Renamed columns: {list(trades.columns)}")        
                
            except (pd.errors.EmptyDataError, ValueError) as e:
                print(f"❌ Error reading CSV file: {e} - falling back to MT4")
                # Fall back to MT4 if CSV reading fails
                mt4 = EACommunicator_API()
                mt4.Connect()
                trades = mt4.Get_all_closed_positions()

            except Exception as e:
                print(f"❌ Unexpected error reading CSV: {e} - falling back to MT4")
                mt4 = EACommunicator_API()
                mt4.Connect()
                trades = mt4.Get_all_closed_positions()    
        else:        
             # If CSV doesn't exist, get from MT4 and it will create the file
            mt4 = EACommunicator_API()
            mt4.Connect()
            trades = mt4.Get_all_closed_positions()

        if trades is None or trades.empty:
            if update.message:
                await update.message.reply_text("❌ No closed trades found.")
            elif update.callback_query:
                await update.callback_query.message.reply_text("❌ No closed trades found.")
            return
        
         # Ensure we have the expected column structure
        if len(trades.columns) == 0:
            await update.message.reply_text("❌ No data columns found in trades.")
            return
        
        # If columns are unnamed, assign proper names based on position
        if trades.columns[0] == 'Unnamed: 0' or trades.columns[0].startswith('0'):
            # Create proper column names based on typical MT4 export order
            expected_columns = [
                'ticket', 'symbol', 'position_type', 'openprice', 'closeprice',
                'profit', 'opentime', 'closetime', 'comment'
            ]
            
            # Only rename as many columns as we have
            rename_dict = {}
            for i, col in enumerate(trades.columns):
                if i < len(expected_columns):
                    rename_dict[col] = expected_columns[i]

            trades = trades.rename(columns=rename_dict)
            print(f"📝 Assigned column names: {list(trades.columns)}")        

        trades['closetime'] = pd.to_datetime(trades['closetime'], errors='coerce')
        trades['profit'] = pd.to_numeric(trades['profit'], errors='coerce')

        # Drop rows with invalid close times
        trades = trades[trades['closetime'].notna()]

        # Only include valid trading activity (exclude deposits, withdrawals, balance adjustments)
        valid_trades = trades[
            trades['symbol'].notna() & 
            (trades['symbol'].str.strip() != "") & 
            (trades['position_type'].isin(["buy", "sell"]))
        ]

        

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

        def calculate_stats(df, label):
            total_profit = df['profit'].sum()
            successful = df[df['profit'] > 0].shape[0]
            unsuccessful = df[df['profit'] <= 0].shape[0]
            return f"*{label}*\n• Total Profit: `${total_profit:.2f}`\n• ✅ Successful Trades: {successful}\n• ❌ Unsuccessful Trades: {unsuccessful}\n"

        daily_trades = valid_trades[valid_trades['closetime'].dt.date == today]
        weekly_trades = valid_trades[valid_trades['closetime'].dt.date >= start_of_week]
        monthly_trades = valid_trades[
            (valid_trades['closetime'].dt.date >= start_of_month) &
            (valid_trades['closetime'].dt.date <= today)
        ]

        last_month_trades = valid_trades[
            (valid_trades['closetime'].dt.date >= last_month_start) &
            (valid_trades['closetime'].dt.date <= last_month_end)
        ]

        print(f"🔍 Last month trades found: {len(last_month_trades)}")
        if not last_month_trades.empty:
            print(f"   Sample close times: {last_month_trades['closetime'].dt.date.iloc[:3].tolist()}")
        
        last_3_months_trades = valid_trades[valid_trades['closetime'].dt.date >= past_3_months]
        last_6_months_trades = valid_trades[valid_trades['closetime'].dt.date >= past_6_months]
        last_year_trades = valid_trades[valid_trades['closetime'].dt.date >= past_1_year]

        msg = (
            "📊 *Trading Statistics*\n\n"
            + calculate_stats(daily_trades, "📅 *Today*")
            + "\n"
            + calculate_stats(weekly_trades, "🗓️ *This Week*")
            + "\n"
            + calculate_stats(monthly_trades, "📆 *This Month*")
            # + "\n"
            # + calculate_stats(last_month_trades, "📉 *Last Month*")
            # + "\n"
            # + calculate_stats(last_3_months_trades, "🪻 *Past 3 Months*") + "\n"
            # + "\n"
            # + calculate_stats(last_6_months_trades, "🌼 *Past 6 Months*") + "\n"
            # + "\n"
            # + calculate_stats(last_year_trades, "📈 *Past 1 Year*")
        )

        if update.message:
            await update.message.reply_text(msg, parse_mode='Markdown')
        elif update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text(msg, parse_mode='Markdown') 

    except Exception as e:
        logger.error(f"Failed to send trading stats: {e}")
        error_msg = "⚠️ Failed to generate trading statistics."
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.callback_query:
            await update.callback_query.message.reply_text(error_msg)

