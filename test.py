from typing import Final
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

TOKEN: Final = '7759076862:AAHPJrG22OFySb3cGhrPkNM8I7lfwxvm8Rk'
BOT_USERNAME: Final = 'FFUCryptBot'

# States for conversation
DEPOSIT_AMOUNT, WITHDRAW_AMOUNT, WITHDRAW_ADDRESS = range(3)

# Simulated user balances (replace with DB in production)
user_balances = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("💰 Deposit", callback_data='deposit'),
            InlineKeyboardButton("💸 Withdraw", callback_data='withdraw')
        ],
        [
            InlineKeyboardButton("📊 My Account", callback_data='account'),
            InlineKeyboardButton("❓ Help", callback_data='help')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome to Crypto Father Bot\n\nClick one of the options below:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'deposit':
        await query.message.reply_text("Please enter the amount you deposited (minimum 20 USDT):")
        return DEPOSIT_AMOUNT

    elif data == 'withdraw':
        await query.message.reply_text("Please enter the amount you wish to withdraw (minimum 100 USDT):")
        return WITHDRAW_AMOUNT

    elif data == 'account':
        user_id = update.effective_user.id
        balance = user_balances.get(user_id, 0)
        await query.message.reply_text(f"📊 Your current balance is: {balance} USDT")

    elif data == 'help':
        await query.message.reply_text("❓ For support, contact @CryptoFatherSupport")

    return ConversationHandler.END

async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        if amount < 20:
            await update.message.reply_text("❌ Minimum deposit is 20 USDT. Try again.")
            return ConversationHandler.END
        user_id = update.effective_user.id
        user_balances[user_id] = user_balances.get(user_id, 0) + amount
        await update.message.reply_text(f"✅ Deposit of {amount} USDT recorded successfully.\n\nYour new balance is: {user_balances[user_id]} USDT")
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")

    return ConversationHandler.END

async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        user_id = update.effective_user.id
        balance = user_balances.get(user_id, 0)

        if amount < 100:
            await update.message.reply_text("❌ Minimum withdrawal is 100 USDT.")
            return ConversationHandler.END

        if amount > balance:
            await update.message.reply_text("❌ You do not have enough balance for this withdrawal.")
            return ConversationHandler.END

        context.user_data['withdraw_amount'] = amount
        await update.message.reply_text("Please enter the USDT address to receive your funds:")
        return WITHDRAW_ADDRESS

    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return ConversationHandler.END

async def withdraw_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text
    user_id = update.effective_user.id
    amount = context.user_data['withdraw_amount']

    user_balances[user_id] -= amount

    await update.message.reply_text(
        f"✅ Withdrawal of {amount} USDT to {address} recorded successfully.\nYour new balance is: {user_balances[user_id]} USDT."

    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('❌ Operation cancelled.')
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start))

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount),
        ],
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_address)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

    print("CryptoFather Bot is running...")
    
    print('Polling for updates...')
    app.run_polling(poll_interval=3)

if __name__ == '__main__':
    main()
