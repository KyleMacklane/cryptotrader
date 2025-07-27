            InlineKeyboardButton("📈 Trading Stats", callback_data='tradingstats')


async def trading_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        mt4 = EACommunicator_API()
        mt4.Connect()
        trades = mt4.Get_all_closed_positions()

        if trades is None or trades.empty:
            if update.message:
                await update.message.reply_text("❌ No closed trades found.")
            elif update.callback_query:
                await update.callback_query.message.reply_text("❌ No closed trades found.")
            return
        



        trades['closetime'] = pd.to_datetime(trades['closetime'])
        trades['profit'] = pd.to_numeric(trades['profit'], errors='coerce')

        # Only include valid trading activity (exclude deposits, withdrawals, balance adjustments)
        valid_trades = trades[
            trades['symbol'].notna() & 
            (trades['symbol'].str.strip() != "") & 
            (trades['position_type'].isin(["buy", "sell"]))
        ]

        now = datetime.now()
        today = now.date()
        start_of_week = (today - timedelta(days=today.weekday()))
        start_of_month = today.replace(day=1)

        def calculate_stats(df, label):
            total_profit = df['profit'].sum()
            successful = df[df['profit'] > 0].shape[0]
            unsuccessful = df[df['profit'] <= 0].shape[0]
            return f"*{label}*\n• Total Profit: `${total_profit:.2f}`\n• ✅ Successful Trades: {successful}\n• ❌ Unsuccessful Trades: {unsuccessful}\n"

        daily_trades = valid_trades[valid_trades['closetime'].dt.date == today]
        weekly_trades = valid_trades[valid_trades['closetime'].dt.date >= start_of_week]
        monthly_trades = valid_trades[valid_trades['closetime'].dt.date >= start_of_month]

        msg = (
            "📊 *Trading Statistics*\n\n"
            + calculate_stats(daily_trades, "📅 *Daily*")
            + "\n"
            + calculate_stats(weekly_trades, "🗓️ *Weekly*")
            + "\n"
            + calculate_stats(monthly_trades, "📆 *Monthly*")
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


    app.add_handler(CallbackQueryHandler(trading_stats, pattern='^tradingstats$'))
