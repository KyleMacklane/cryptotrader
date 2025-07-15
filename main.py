import os
from typing import Final
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from account_manager import AccountManager 
from datetime import datetime
from transaction_logger import TransactionLogger
from trade_reconciler import TransactionLogger
import re

def escape_markdown(text):
    # Escape all Telegram MarkdownV2 special characters
    return re.sub(r'([_*\[\]()~`>#+=|{}.!-])', r'\\\1', str(text))


tx_logger = TransactionLogger()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
TOKEN ='7759076862:AAHPJrG22OFySb3cGhrPkNM8I7lfwxvm8Rk'
BOT_USERNAME: Final = os.getenv('BOT_USERNAME')
COMMUNITY_LINK: Final = os.getenv('COMMUNITY_LINK')
ADMIN_IDS = [5079683472] 
DEPOSIT_AMOUNT, WITHDRAW_AMOUNT, WITHDRAW_ADDRESS, TRANSACTION_HASH = range(4)
REFERRAL_BONUS_PERCENT=10

PROFIT_CONFIG = {
    'daily': 2.0,
    'weekly': 21.0,
    'monthly': 84.32
}

WALLETS = {
    'USDT_TRC20': os.getenv('USDT_TRC20'),
    'USDT_BEP20': os.getenv('USDT_BEP20'),
    'USDC_BEP20': os.getenv('USDC_BEP20')
}

FAQ_TEXT = """
📚 *Frequently Asked Questions*

🔹 *How the Bot Works*
The BOT replicates proven trading strategies with...

🔹 *Estimated Earnings*
$1000 → Day 7: $1149
$1000 → Day 28: $1741

🔹 *Risk Management*
- 2% daily stop loss
- No leverage used
"""

account_manager = AccountManager("accounts.csv")  

# Menus
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📂 Account Info", callback_data='account_info'),
            InlineKeyboardButton("💵 Deposit", callback_data='deposit')
        ],
        [
            InlineKeyboardButton("💸 Withdraw", callback_data='withdraw'),
            InlineKeyboardButton("📞 Support", callback_data='support')
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data='main_menu')
        ]
    ])

def back_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]
    ])

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 View All Balances", callback_data="admin_view_balances")],
        [InlineKeyboardButton("🔄 Process Withdrawals", callback_data="admin_process_withdrawals")],
        [InlineKeyboardButton("📋 Pending Deposits", callback_data="admin_pending_deposits")]
    ])
    await update.message.reply_text(
        "Admin Panel:",
        reply_markup=keyboard
    )

# Flow starters
async def start_deposit_flow(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    msg = update_or_query.message if hasattr(update_or_query, 'message') else update_or_query
    await msg.reply_text("Please enter the amount you deposited (minimum 20 USDT):")
    return DEPOSIT_AMOUNT

async def start_withdraw_flow(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    msg = update_or_query.message if hasattr(update_or_query, 'message') else update_or_query
    await msg.reply_text("Please enter the amount you wish to withdraw (minimum 23 USDT):")
    return WITHDRAW_AMOUNT

# Account Info
async def show_account(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    # Get user ID from either Update or CallbackQuery
    if isinstance(update_or_query, Update):  # For command messages
        user_id = str(update_or_query.effective_user.id)
        msg = update_or_query.message
    else:  # For CallbackQuery
        user_id = str(update_or_query.from_user.id)
        msg = update_or_query.message  # Access message from callback query
    
    # Get account info
    account_info = account_manager.get_account_info(user_id)
    
    if not account_info:
        # Create new account if doesn't exist
        account_manager.add_user_if_not_exists(user_id, "main", user_id)
        account_info = account_manager.get_account_info(user_id)
        if not account_info:  # If still None after creation
            error_msg = "❌ Could not create or retrieve account. Please contact support."
            if isinstance(update_or_query, CallbackQuery):
                await update_or_query.edit_message_text(error_msg)
            else:
                await msg.reply_text(error_msg)
            return
        
    # Format response
    response = (
        "📊 *Account Information*\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"💰 Current Balance: *{account_info['balance']} USDT*\n\n"
        f"💸 Total Withdrawals: *{account_info.get('total_withdrawals', '0')} USDT*\n"   
        f"🔗 Referral ID: `{account_info.get('referral_id', 'N/A')}`\n"
        "_Note: All deposits and withdrawals include a 5% fee._"

    )
    
    # Send or edit message appropriately
    if isinstance(update_or_query, CallbackQuery):
        await update_or_query.edit_message_text(
            text=response,
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
    else:
        await msg.reply_text(
            text=response,
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
        
        
# Support Info
async def show_help(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    msg = update_or_query.message if hasattr(update_or_query, 'message') else update_or_query
    await msg.reply_text("❓ For support, contact @CryptoFatherSupport")

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    account_manager.add_user_if_not_exists(user.id, "main", str(user.id))
    await update.message.reply_text(
        """*Welcome to Crypto Father Bot*  
We’re excited to introduce you to a powerful and profitable trading experience\\.

*Why Choose Crypto Father Bot?*
✅ Secure & Legitimate – Developed in 2025  
⚡️ 15% Profit in just 24 hours  
💰 Accepts USDT & major crypto

*How It Works:*
• Deposit a minimum of 20 USDT  
• Wait just 24 hours

*Deposit & Returns (15% Profit)*  
20 ➜ 23 USDT  
100 ➜ 115 USDT  
500 ➜ 575 USDT  
1000 ➜ 1150 USDT  
10,000 ➜ 11,500 USDT  
80,000 ➜ 92,000 USDT

*Returns are based on 15% profit margin\\.*  
📅 *Profit Timeframe:* 24 hours""",
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )

# Menu Handler
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'account_info':
        await show_account(query, context)
    elif query.data == 'deposit':
        return await start_deposit_flow(query, context)
    elif query.data == 'withdraw':
        return await start_withdraw_flow(query, context)
    elif query.data == 'support':
        await show_help(query, context)
    elif query.data == 'main_menu':
        await query.edit_message_text(
            text="Main Menu",
            reply_markup=main_menu_keyboard()
        )
    
    return ConversationHandler.END

async def notify_admin_deposit(user_id: int, amount: float, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = await context.bot.get_chat(user_id)
        # Use the gross amount from context instead of the net amount
        gross_amount = context.user_data.get('gross_deposit', amount)
        formatted_amount = f"{gross_amount:.2f}"
        
        with open("pending_deposits.csv", "a") as f:
            f.write(f"{user_id},{gross_amount},{TRANSACTION_HASH},{datetime.now()}\n")

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Verify Deposit", callback_data=f"verify_deposit_{user_id}_{formatted_amount}")],
            [InlineKeyboardButton("❌ Reject Deposit", callback_data=f"reject_deposit_{user_id}_{formatted_amount}")]
        ])
        
        message = (
            f"⚠️ Deposit Verification Needed\n\n"
            f"User: {user.full_name} (@{user.username if user.username else 'N/A'})\n"
            f"ID: {user_id}\n"
            f"Amount: {gross_amount} USDT (User will receive {gross_amount * 0.95:.2f} after 5% fee)\n\n"
            "Please verify the transaction on the exchange.\n\n"
            f"Transaction Hash: `{TRANSACTION_HASH}`\n\n"
        )
        
        for admin_id in ADMIN_IDS:
            await context.bot.send_message(
                chat_id=admin_id,
                text=message,
                reply_markup=keyboard
            )
            
    except Exception as e:
        print(f"Error notifying admin: {e}")
        
#admin helper

async def notify_admin_withdrawal(context: ContextTypes.DEFAULT_TYPE, admin_id: int, user_id: int, amount: float, address: str):
    try:
        user = await context.bot.get_chat(user_id)
        
        message = (
            f"⚠️ Withdrawal Approval Needed\n\n"
            f"User: {user.full_name} (@{user.username if user.username else 'N/A'})\n"
            f"ID: {user_id}\n"
            f"Amount: {amount} USDT\n"
            f"Address: {address}\n\n"
            "Please verify and approve this withdrawal."
        )
        
        await context.bot.send_message(
            chat_id=admin_id,
            text=message,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve_withdraw_{user_id}_{amount}_{address}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_withdraw_{user_id}_{amount}")
                ]
            ])
        )
    except Exception as e:
        logger.error(f"Error notifying admin: {e}")
        
async def handle_admin_verification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
        
        if query.from_user.id not in ADMIN_IDS:
            logger.warning(f"Unauthorized admin attempt by {query.from_user.id}")
            await query.edit_message_text("❌ Admin privileges required")
            return

        # Parse callback data
        parts = query.data.split('_')
        action = parts[0]
        request_type = parts[1]
        user_id = int(parts[2])
        amount = float(parts[3])
        
        if request_type == "deposit":
            # Verify deposit
            if action == "verify":
                tx_logger.update_status(
                    tx_hash=context.user_data.get('tx_hash', ""), 
                    status="COMPLETED",
                    notes="Admin approved"
                )
                
                # Use the gross amount but apply fee when crediting
                gross_amount = amount
                net_amount = gross_amount * 0.95
                
                if not account_manager.update_balance(user_id, net_amount, apply_fee=False):
                    await query.edit_message_text("❌ Failed to update balance")
                    return
                
                tx_logger.log_trade(user_id, "Deposit", gross_amount)
                await query.edit_message_text(f"✅ Verified deposit of {gross_amount} USDT (credited {net_amount:.2f} after fee)")
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"✅ Your deposit of {gross_amount:.2f} USDT has been approved.\n"
                        f"💰 A 5% fee was applied and {net_amount:.2f} USDT has been credited to your account."
                    )   
                )       
            elif action == "reject":
                await query.edit_message_text(f"❌ Rejected deposit of {amount} USDT")
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ Your deposit of {amount} USDT was rejected"
                )
                
        elif request_type == "withdraw":
            if action == "approve":
                address = parts[4] if len(parts) > 4 else "UNKNOWN"

                # First check balance
                account = account_manager.get_account_info(user_id)
                if float(account["balance"]) < amount:
                    await query.edit_message_text("❌ User has insufficient balance")
                    return
                
                if not account_manager.update_balance(user_id, -amount):
                    await query.edit_message_text("❌ Failed to process withdrawal")
                    return
                
                if not account_manager.update_total_withdrawals(user_id, amount):
                    logger.warning(f"Failed to update total withdrawals for {user_id}")

                tx_logger.log_trade(user_id, "Withdrawal", -amount)
                await query.edit_message_text(
                    f"✅ Approved withdrawal of {amount} USDT\n"
                    f"to address: {address}"
                )
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ Your withdrawal of {amount} USDT has been approved!\n"
                         f"Funds will be sent to: {address} in 2-3 hours.\n" 
                )
                
            elif action == "reject":
                await query.edit_message_text(f"❌ Rejected withdrawal of {amount} USDT")
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"⚠️ Your withdrawal of {amount} USDT was rejected\n"
                         "Please contact support if this was unexpected."
                )
                
    except Exception as e:
        logger.error(f"Verification error: {e}")
        await query.edit_message_text("❌ Error processing request")


# Deposit Handler
async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        user_id = str(update.effective_user.id)

        if amount < 20:
            await update.message.reply_text("❌ Minimum deposit is 20 USDT.")
            return DEPOSIT_AMOUNT

           # Store pending deposit
        net_amount = round(amount * 0.95, 2)
        context.user_data['pending_deposit'] = net_amount
        context.user_data['gross_deposit'] = amount  

        
        await update.message.reply_text(
                f"*Please send exactly* `{amount} USDT` *to:*\n\n"
                "*Exchange Address:* `TKokECJSvEW2e2A8wXQzrw3fify9Sfc5RF`\n\n"
                "After sending, please provide the transaction hash.\n\n"
                f"_Note: A 5% deposit fee will be applied. Your credited balance will be {net_amount} USDT_",
                parse_mode='Markdown'
        )

          # Apply referral bonus if first deposit
        account = account_manager.get_account_info(user_id)
        if account and account.get("first_deposit") == "0":
            # Apply referral bonus
            referrer_id = account.get("referrer_id")
            if referrer_id:
                account_manager.add_referral_earning(referrer_id, amount)
        
            # Mark first deposit
            accounts = account_manager._load_accounts()
            for acc in accounts:
                if acc["telegram_id"] == str(user_id):
                 acc["first_deposit"] = "1"
                 account_manager._save_accounts(accounts)
                 break

        return TRANSACTION_HASH 

   
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
    return DEPOSIT_AMOUNT


async def receive_transaction_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tx_hash = update.message.text
    user_id = update.effective_user.id
    amount = context.user_data.get('pending_deposit')
    tx_logger.log_trade(
        user_id=str(user_id),
        tx_type="DEPOSIT",
        amount=amount,
        tx_hash=tx_hash,
        notes="Pending admin verification (Gross: {gross} USDT, Net: {amount} USDT)"
    )
    if not amount:
        await update.message.reply_text("❌ No pending deposit found. Please start the deposit process again.")
        return ConversationHandler.END

    
    # Notify admin
    await notify_admin_deposit(user_id, amount, context)
    
    await update.message.reply_text(
        "⌛ Your deposit is under verification by our team.\n"
        "We'll notify you once it's processed (usually within 15-30 minutes).\n\n"
        f"Transaction Hash: `{tx_hash}`",
        parse_mode='Markdown',
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

# Withdraw Handler
async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        user_id = str(update.effective_user.id)
        balance = account_manager.get_balance(user_id)  
        # locked = account_manager.get_locked_funds(user_id)
        # available_balance = balance - locked

        if amount < 23:
            await update.message.reply_text("❌ Minimum withdrawal is 23 USDT.")
            return WITHDRAW_AMOUNT
        
        if amount > balance:
            await update.message.reply_text("❌ Insufficient balance.")
            return WITHDRAW_AMOUNT
        # if amount > available_balance:
        #     await update.message.reply_text("❌ Funds locked (minimum 30-day holding period)")
            
        net_amount = round(amount * 0.95, 2)
        context.user_data['withdraw_amount'] = amount
        context.user_data['withdraw_net_amount'] = net_amount

        await update.message.reply_text(
            f"✅ Withdrawal request accepted.\n"
            f"You will receive {net_amount} USDT after a 5% fee.\n\n"
            "Now, enter your USDT wallet address:"
        )
        return WITHDRAW_ADDRESS
    
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return WITHDRAW_AMOUNT

async def withdraw_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text
    user_id = update.effective_user.id
    amount = context.user_data.get('withdraw_amount')
    net_amount = amount * 0.95
    
    # Store withdrawal request
    context.user_data['withdraw_address'] = address
    
    # Notify admin for approval
    for admin_id in ADMIN_IDS:
        await notify_admin_withdrawal(context, admin_id, user_id, amount, address)
    
    await update.message.reply_text(
        f"⌛ Your withdrawal request of {amount:.2f} USDT (you'll receive {net_amount:.2f} USDT after fees) "
        "has been submitted for admin approval.\n"
        "You'll receive a notification once processed.",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END

async def reconcile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    # Get reconciliation report
    recon_report = tx_logger.full_reconciliation()
    
    # Build report message
    message = "🔍 *Trade Reconciliation Report*\n\n"
    discrepancies = 0
    
    for user_id, calculated_balance in recon_report.items():
        account = account_manager.get_account_info(user_id)
        if not account:
            message += f"❌ User {user_id}: No account found\n"
            discrepancies += 1
            continue
            
        actual_balance = float(account.get("balance", 0))
        
        if abs(actual_balance - calculated_balance) > 0.01:
            message += (
                f"⚠️ User {user_id}:\n"
                f"  Calculated: {calculated_balance:.2f} USDT\n"
                f"  Actual: {actual_balance:.2f} USDT\n"
                f"  Difference: {actual_balance - calculated_balance:.2f} USDT\n\n"
            )
            discrepancies += 1
    
    if discrepancies == 0:
        message = "✅ All accounts balanced perfectly!"
    else:
        message += f"\nFound {discrepancies} discrepancies"
    
    await update.message.reply_text(
        message,
        parse_mode='Markdown'
    )
def get_trading_stats():
    """Generates formatted trading statistics"""
    return (
        "📊 *Trading Statistics*\n\n"
        f"📅 Daily Profit: {PROFIT_CONFIG['daily']}%\n"
        f"📆 Weekly Profit: {PROFIT_CONFIG['weekly']}%\n"
        f"💰 Monthly Profit: {PROFIT_CONFIG['monthly']}%\n\n"
        "_Updated: " + datetime.now().strftime("%Y-%m-%d %H:%M") + "_"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        get_trading_stats(),
        parse_mode='Markdown'
    )


async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ref_info = account_manager.get_referral_info(user_id)
    
    if not ref_info:
        await update.message.reply_text("❌ Account not found")
        return
    
    referral_id = escape_markdown(ref_info["referral_id"])
    referral_count = escape_markdown(ref_info["referral_count"])
    referral_earnings = escape_markdown(ref_info["referral_earnings"])
    bot_username = escape_markdown(BOT_USERNAME)

    message = (
        "👥 *Your Referral Program*\n\n"
        f"🆔 Your Referral ID: `{referral_id}`\n"
        f"👤 Referrals: {referral_count}\n"
        f"💰 Earnings: {referral_earnings} USDT\n\n"
        f"Share your link: https://t\\.me/{bot_username}?start\\=ref\\_{referral_id}\n\n"
        "_Earn 10% of your referrals' first deposit_"
    )
    await update.message.reply_text(
        message,
        parse_mode='MarkdownV2',
        reply_markup=main_menu_keyboard()
    )

async def handle_referral_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref_id = None
    
    # Extract referral ID from deep link
    if context.args and context.args[0].startswith('ref_'):
        ref_id = context.args[0][4:]
    
    # Create account with referral if applicable
    account_manager.add_user_if_not_exists(user.id, "main", str(user.id), ref_id)

        # Send welcome message
    await start(update, context)
    
    # Notify referrer
    if ref_id:
        for account in account_manager._load_accounts():
            if account.get("referral_id") == ref_id:
                referrer_id = account["telegram_id"]
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 New referral! @{user.username} joined using your link"
                )
                break

async def show_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "🔷 *Available Wallets*\n\n"
        "💠 USDT (TRC20):\n`" + WALLETS['USDT_TRC20'] + "`\n\n"
        "💠 USDT (BEP20):\n`" + WALLETS['USDT_BEP20'] + "`\n\n"
        "💠 USDC (BEP20):\n`" + WALLETS['USDC_BEP20'] + "`"
    )
    await update.message.reply_text(message, parse_mode='Markdown')

async def faq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(FAQ_TEXT, parse_mode='Markdown')

async def community_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join Investor Chat", url=COMMUNITY_LINK)]
    ])
    await update.message.reply_text(
        "💬 Join our private investor community:",
        reply_markup=keyboard
    )
# Cancel Handler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

# async def test_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Test command: /testnotify"""
#     if update.effective_user.id not in ADMIN_IDS:
#         return
#     await notify_admin_deposit(update.effective_user.id, 50.0, context)
#     await update.message.reply_text("Test notification sent")

# async def check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Check if you're an admin: /amIadmin"""
#     is_admin = update.effective_user.id in ADMIN_IDS
#     await update.message.reply_text(f"Admin status: {is_admin}\nYour ID: {update.effective_user.id}")




# Main
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', handle_referral_start))
    # app.add_handler(CommandHandler("testnotify", test_notify))
    # app.add_handler(CommandHandler("amIadmin", check_admin))
    app.add_handler(CallbackQueryHandler(
        handle_admin_verification, 
        pattern=r"^(approve|reject|verify)_(withdraw|deposit)_\d+_\d+(\.\d+)?(_\w+)?$"
    ))
    app.add_handler(CommandHandler("admin", admin_menu))
    app.add_handler(CommandHandler('deposit', start_deposit_flow))
    app.add_handler(CommandHandler('withdraw', start_withdraw_flow))
    app.add_handler(CommandHandler('account', show_account))
    app.add_handler(CommandHandler('help', show_help))
    app.add_handler(CommandHandler('stats', stats_command))
    app.add_handler(CommandHandler('referral', referral_command))
    app.add_handler(CommandHandler('wallets', show_wallets))
    app.add_handler(CommandHandler('faq', faq_command))
    app.add_handler(CommandHandler('community', community_command))
    app.add_handler(CommandHandler('reconcile', reconcile_command))

    TRANSACTION_HASH = 3
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), CallbackQueryHandler(handle_menu)],
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            TRANSACTION_HASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_transaction_hash)],
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_address)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(handle_menu, pattern='^main_menu$')
        ],
        allow_reentry=True
    )
    app.add_handler(conv_handler)

    print("Bot is running...\nPolling for updates...")
    app.run_polling()

if __name__ == '__main__':
    main()
