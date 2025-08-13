import os
from typing import Final, Optional
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.error import BadRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from account_manager import AccountManager 
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from trade_reconciler import TransactionLogger
import re
import io
import pandas as pd
from pathlib import Path
import uuid


from withdraws.withdraw_tracker import WithdrawalTracker
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from functools import wraps
import asyncio
from mt5.EACommunicator_API import EACommunicator_API

def synchronized_lock(lock_name):
    def decorator(f):
        @wraps(f)
        async def wrapped(*args, **kwargs):
            lock = getattr(wrapped, '_lock', None)
            if lock is None:
                lock = asyncio.Lock()
                setattr(wrapped, '_lock', lock)
                
            async with lock:
                return await f(*args, **kwargs)
        return wrapped
    return decorator

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
# TOKEN = '7603656998:AAHYKMQN9UQLfZ9Dm_Z7759076862:AAHPJrG22OFySb3cGhrPkNM8I7lfwxvm8Rk3RxgSyIMgZvQdNes'
BOT_USERNAME: Final = 'FFUCryptBot'
COMMUNITY_LINK = "https://t.me/Unclesbotsupport"
ADMIN_IDS = [5079683472]  
DEPOSIT_AMOUNT, WITHDRAW_AMOUNT, WITHDRAW_ADDRESS, TXN_PROOF = range(4)
EDIT_USER_BALANCE = range(1)
REFERRAL_BONUS_PERCENT=2
PROFIT_FEE_RATE = 0.10 
MAX_WITHDRAWALS_PER_MONTH = 1
WITHDRAWAL_COOLDOWN = timedelta(days=30)
MIN_DEPOSIT = 100
MIN_WITHDRAWAL = 50

PROFIT_CONFIG = {
    'daily': 2.0,
    'weekly': 21.0,
    'monthly': 84.32
}



WALLETS = {
'USDT_TRC20':'TKNmRYfT9zRMr2k8HdbiZpQCGC516TM8iS',
'USDT_BEP20':'0xe84fbba6e929f752f338ee90c90bc427337f6df8',
'USDC_BEP20':'CONTACT SUPPORT FOR USDC WALLET',
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
INTEREST_RATE = 0.15  # 15% daily
INTEREST_INTERVAL = timedelta(days=1)
INTEREST_FEE_RATE = 0.10  # 10% fee on earned interest

account_manager = AccountManager("accounts.csv") 
withdrawal_tracker = WithdrawalTracker()

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
            InlineKeyboardButton("📜 History", callback_data='history'),
            InlineKeyboardButton("📈 Trading Stats", callback_data='tradingstats')
        ],
        [
            InlineKeyboardButton("🔗 Referral", callback_data='referral'),
            
        ],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data='main_menu')
        ]
    ])



async def transaction_history(update: Update, context: ContextTypes.DEFAULT_TYPE,page:int=0):
    if hasattr(update, 'callback_query') and update.callback_query:
        # Handle callback query case
        user_id = update.callback_query.from_user.id
        message = update.callback_query.message
        is_callback = True
    else:
        # Handle regular message case
        user_id = update.effective_user.id
        message = update.message
        is_callback = False

    txns = tx_logger.get_user_transactions(
        user_id,
        limit=1000,
    )

    
    if txns.empty:
        if message:
            await message.reply_text("📭 No transaction history found")
        elif update.callback_query:
            await update.callback_query.edit_message_text("📭 No transaction history found")
        return
    
    pages = [txns[i:i+5] for i in range(0, len(txns), 5)]
    total_pages = len(pages)
    page = max(0,min(page,total_pages -1))
    txns = pages[page]
    
    response = f"📜 Your Transaction History (Page {page + 1}/{total_pages}):\n\n"    

    for _, txn in txns.iterrows():
        amount = float(txn['amount'])
        txn_type = txn['tx_type']
        status = txn['status']
        address= txn['address']
        date = pd.to_datetime(txn['timestamp']).strftime('%Y-%m-%d %H:%M')
        
        emoji = "💵" if amount >= 0 else "💸"
        verb = "Deposited" if amount >= 0 else "Withdrew"
        address_line = f"Address: {address}\n" if txn_type.upper() == "WITHDRAW" else ""
        
        response += (
            
            f"{emoji} *{txn_type}* ({status})\n"
            f"Amount: {abs(amount):.2f} USDT\n"
            f"{address_line}"
            f"Date: {date}\n"
            f"-------------------------------------------------\n"
        )

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"history_page_{page-1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"history_page_{page+1}"))    

    keyboard = [buttons] if buttons else []
    keyboard.append([InlineKeyboardButton("📤 Export Full History", callback_data="export_history")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu",callback_data="main_menu")])


    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_callback and update.callback_query:
        await update.callback_query.edit_message_text(
            text=response,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await message.reply_text(
            text=response,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

async def export_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    txns = tx_logger.get_user_transactions(user_id, limit=1000)
    txns.to_csv("debug_export.csv", index=False)

    
    if txns.empty:
        if update.callback_query:
            await update.callback_query.answer("You have no transactions to export", show_alert=True)
        else:
            await update.message.reply_text("You have no transactions to export")
        return
    
    logger.info(f"Exporting {len(txns)} transactions for user {user_id}")

    
    # Create CSV in memory
    
    bio=io.BytesIO()
    csv_data = txns.to_csv(index=False).encode()
    bio.write(csv_data)
    bio.seek(0)


    # For callback queries, we need to answer first
    
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.message.reply_document(
                document=bio, 
                filename="transaction_history.csv",
                caption="Your full transaction history"
            )
            logger.info("Export completed successfully")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            await update.effective_message.reply_text(f"⚠️ Export failed: {str(e)}")   
    else:
        try:
            await update.message.reply_document(
                document=bio,
                filename="transaction_history.csv",
                caption="Your full transaction history"
            )
            logger.info("Export completed successfully")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            await update.effective_message.reply_text(f"⚠️ Export failed: {str(e)}")    



def back_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='main_menu')]
    ])

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    keyboard = InlineKeyboardMarkup([
        # [InlineKeyboardButton("📊 View All Balances", callback_data="admin_view_balances")],
        [InlineKeyboardButton("✏️ View User Balance", callback_data="admin_edit_balance")],
        # [InlineKeyboardButton("🔄 Process Withdrawals", callback_data="admin_process_withdrawals")],
        # [InlineKeyboardButton("📋 Pending Deposits", callback_data="admin_pending_deposits")]
    ])
    await update.message.reply_text(
        "Admin Panel:",
        reply_markup=keyboard
    )

# Flow starters
async def start_deposit_flow(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    msg = update_or_query.message if hasattr(update_or_query, 'message') else update_or_query
    await msg.reply_text("Please enter the deposit amount  (minimum 100 USDT):")
    return DEPOSIT_AMOUNT

async def start_withdraw_flow(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    msg = update_or_query.message if hasattr(update_or_query, 'message') else update_or_query
    await msg.reply_text("Please enter the amount you wish to withdraw (minimum 50 USDT):")
    return WITHDRAW_AMOUNT

   
        
        #  check ROI status

def check_roi_status(user_id):
    account = account_manager.get_account_info(user_id)
    if not account:
        return False
        
    total_deposits = float(account.get("total_deposits", 0))
    total_profits = float(account.get("total_interest", 0))
  
    
    # ROI is achieved when profits >= deposits
    return total_deposits > 0 and total_profits >= total_deposits


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
        total_interest = account_info.get("total_interest", "0.00")
        if not account_info:  # If still None after creation
            error_msg = "❌ Could not create or retrieve account. Please contact support."
            if isinstance(update_or_query, CallbackQuery):
                await update_or_query.edit_message_text(error_msg)
            else:
                await msg.reply_text(error_msg)
            return
        
  
    
    # Get withdrawal data
    withdrawal_data = withdrawal_tracker._load_data()
    user_data = next((item for item in withdrawal_data if item["user_id"] == user_id), None)

    last_withdrawal = "Never"
    withdrawals_this_month = 0
    if user_data:
        last_withdrawal = user_data["last_withdrawal_date"]
        withdrawals_this_month = user_data["withdrawals_this_month"]


    # Safely get all values with defaults
    

    balance = account_info.get('balance', '0.00')
    total_withdrawals = account_info.get('total_withdrawals', '0.00')
    total_interest = account_info.get('total_interest', '0.00') 

    total_deposits = account_info.get('total_deposits', '0.00')
    floating_pl = account_manager.get_floating_pl()
    closed_pl = account_manager.get_closed_pl()
    # Format response
    response = (
        "📊 *Account Information*\n\n"
        f"👤 ACCOUNT ID: `{user_id}`\n\n"
        f"💰 CURRENT BALANCE: `{balance} USD`\n\n"
        f"🔗 TOTAL DEPOSITS: `{total_deposits}`\n\n"
        # f"📈 FLOATING P/L: *{floating_pl:.2f} USDT*\n"
        # f"💹 REALIZED P/L: *{closed_pl:.2f} USDT*\n"
        # f"🏦 CURRENT EQUITY: *{equity:.2f} USDT*\n\n"
        f"💸 PROFITS EARNED: `{total_interest} USD`\n\n"
        # f"🔒 WITHDRAW STATUS: `{'Unlocked' if check_roi_status(user_id) else 'Locked'}`\n\n"
        f"💸 TOTAL WITHDRAWS: `{total_withdrawals} USD`\n\n"
        f"📅 LAST WITHDRAW: `{last_withdrawal}`\n\n"
        f"🔄 WITHDRAWS THIS MONTH: `{withdrawals_this_month}/{MAX_WITHDRAWALS_PER_MONTH}`\n\n"      
        # f"🔗 REFERRAL ID `{referral_id}`\n\n"
        "_Note: All deposits and withdrawals include a 10% fee._\n\n"
    )
    

       # Connect to MT4 and get live balance   
    # mt4 =  EACommunicator_API

    # def get_mt4_balance():
    #     """Gets current account equity (balance + floating P/L)"""
    #     mt4 = EACommunicator_API()
    #     try:
    #         mt4.Connect()
    #         return mt4.Get_account_balance()  
    #     except Exception as e:
    #         logger.error(f"MT4 equity check failed: {str(e)}")
    #         raise
    #     finally:
    #         mt4.Disconnect()    
    # try:
    #     mt4_balance = get_mt4_balance
    #     response += f"\n🔹 COLLECTIVE POOL: *{mt4_balance:.2f} USD*"
    # except Exception as e:
    #     logger.error(f"Failed to get MT4 balance: {e}")
    #     response += "\n🔹 COLLECTIVE POOL: Unavailable"


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
    await msg.reply_text("❓ For support, contact @Unclesbotsupport")

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    account_manager.add_user_if_not_exists(user.id, "main", str(user.id))
    await update.message.reply_text(
        """*WELCOME TO UNCLE HARD SCALPING BOT, PLEASE READ CAREFULLY BEFORE INVESTING*.

        INVESTING INVOLVES RISKS, DON'T INVEST BORROWED OR EMERGENCY FUNDS !!
        *How It Works:*
        a) 1 to 2 % daily earnings SOMETIMES few losses (real tradinG).
        b) 10% on deposits.
        c) 10 % + gas fee on withdrawals .
        d) minimum deposits  100 $and withdrawals are 50$.
        e) Deposits are locked to avoid account liqudations and unlocked on return on investment. 
        f) Only  1 withdrawal is allowed per month. 
        g) withdrawals are processed within 24hrs, no delays.


        By continuing you agree to the above terms, welcome aboard.""",
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
    elif query.data == 'referral':
        await referral_command(update, context)    
    elif query.data == 'admin_edit_balance':
        return await list_all_users(query, context)  
    elif query.data == 'history':
        await transaction_history(update, context) 
    elif query.data == "export_history":
        await export_history(update,context) 
    elif query.data.startswith("history_page_"):
        try:
            page = int(query.data.split("_")[-1])
        except ValueError:
            page = 0  
            
        await transaction_history(update, context, page)    
    elif query.data == 'main_menu':
        await query.edit_message_text(
            text="Main Menu",
            reply_markup=main_menu_keyboard()
        )
   
    
    return ConversationHandler.END




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
        start_of_month = today.replace(day=1) #This gives us the first day of the current month, regardless of what today's day is.
        last_month_end = start_of_month - timedelta(days=1) # We then subtract one day from that to get the last day of last month
        last_month_start = last_month_end.replace(day=1) # And we replace that with  again to get the first day of last month
        
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
        monthly_trades = valid_trades[valid_trades['closetime'].dt.date >= start_of_month]
        
        last_month_trades = valid_trades[
            (valid_trades['closetime'].dt.date >= last_month_start) &
            (valid_trades['closetime'].dt.date <= last_month_end)
        ]
        
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
            + "\n"
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


async def list_all_users(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    accounts = account_manager._load_accounts()
    
    if not accounts:
        if hasattr(update_or_query, 'message'):
            await update_or_query.message.reply_text("❌ No users found")
        elif hasattr(update_or_query, 'edit_message_text'):
            await update_or_query.edit_message_text("❌ No users found")
        else:
            await context.bot.send_message(chat_id=update_or_query.effective_chat.id, text="❌ No users found")
        return

    context.user_data['all_accounts'] = accounts
    context.user_data['current_page'] = 0

    await display_accounts_page(update_or_query, context)
    return EDIT_USER_BALANCE  


async def display_accounts_page(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    accounts = context.user_data['all_accounts']
    current_page = context.user_data['current_page']
    per_page = 5
    total_pages = (len(accounts) + per_page - 1) // per_page
    
    start_idx = current_page * per_page
    end_idx = start_idx + per_page
    page_accounts = accounts[start_idx:end_idx]
    
    message = "👥 All Users (Page {}/{})\n\n".format(current_page + 1, total_pages)
    buttons = []
    for acc in page_accounts:
        balance = float(acc.get('balance', 0))
        message += "🆔: `{}` | 💰: ${:.2f}\n".format(acc['telegram_id'], balance)
        buttons.append([InlineKeyboardButton(
            f"Edit {acc['telegram_id']}",
            callback_data=f"edit_user_{acc['telegram_id']}"
        )])
    
    # pagination controls
    pagination_buttons = []
    if current_page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="prev_page"))
    if end_idx < len(accounts):
        pagination_buttons.append(InlineKeyboardButton("Next ➡️", callback_data="next_page"))

    if pagination_buttons:
            buttons.append(pagination_buttons)
        
    buttons.append([InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_menu")])
        
    try:   
        if hasattr(update_or_query, 'edit_message_text'):
            await update_or_query.edit_message_text(
                text=message,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(buttons)
                )
        else:
            msg = getattr(update_or_query, 'message', None)
            if msg:
                await msg.reply_text(
                    text=message,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
            else:
                await context.bot.send_message(
                    chat_id=update_or_query.effective_chat.id,
                    text=message,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
    except Exception as e:
        logger.error(f"Error displaying accounts page: {e}")
        # Fallback to simple message if rich display fails
        if hasattr(update_or_query, 'message'):
            await update_or_query.message.reply_text("Error displaying user list")
        else:
            await update_or_query.reply_text("Error displaying user list")     



async def edit_user_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.data.split('_')[-1]
    context.user_data['edit_user_id'] = user_id
    
    await query.edit_message_text(
        f"Editing user {user_id}\n\n"
        "Send me the new balance amount:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="cancel_edit")]
        ])
    )
    return EDIT_USER_BALANCE

# async def search_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     query = update.callback_query
#     await query.answer()
    
#     await query.edit_message_text(
#         "Send me the user ID or username to search for:",
#         reply_markup=InlineKeyboardMarkup([
#             [InlineKeyboardButton("🔙 Cancel", callback_data="admin_menu")]
#         ])
#     )
#     return SEARCH_USERS

#process deposit for admin balace edit
async def process_new_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = context.user_data['edit_user_id']
        new_balance = float(update.message.text)
        
        if account_manager.set_balance(user_id, new_balance):
            await update.message.reply_text(
                f"✅ Updated balance for user {user_id} to ${new_balance:.2f}",
                reply_markup=back_menu_keyboard()
            )     
              # Log this admin action
            admin_id = update.effective_user.id
            tx_logger.log_trade(
                user_id=user_id,
                tx_type="UPDATE",
                amount=new_balance,
                notes=f"Edited by admin {admin_id}"
            )
        else:
            await update.message.reply_text("❌ Failed to update balance")
            
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number")
        return EDIT_USER_BALANCE

    return ConversationHandler.END 

async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Edit cancelled", reply_markup=back_menu_keyboard())
    return ConversationHandler.END

async def handle_page_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()   
    if query.data == "prev_page":
        context.user_data['current_page'] -= 1
    elif query.data == "next_page":
        context.user_data['current_page'] += 1
    
    await display_accounts_page(query, context)
    return EDIT_USER_BALANCE


async def notify_admin_deposit(user_id: int, amount: float, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = await context.bot.get_chat(user_id)
        # Use the gross amount from context instead of the net amount
        gross_amount = context.user_data.get('deposit_data', {}).get('gross_amount', amount)

        formatted_amount = f"{float(gross_amount):.2f}"
        tx_id = context.user_data.get('deposit_data', {}).get('tx_id', str(uuid.uuid4())[:8])


      
        
        with open("pending_deposits.csv", "a") as f:
            f.write(f"{user_id},{user.username},{gross_amount},{tx_id},{datetime.now()}\n")

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Verify Deposit", callback_data=f"verify_deposit_{user_id}_{formatted_amount}_{tx_id}")],
            [InlineKeyboardButton("❌ Reject Deposit", callback_data=f"reject_deposit_{user_id}_{formatted_amount}_{tx_id}")]
        ])
        
        message = (
            f"⚠️ Deposit Verification Needed\n\n"
            f"User: {user.full_name} (@{user.username if user.username else 'N/A'})\n"
            f"ID: {user_id}\n"
            f"Amount: {gross_amount} USDT (User will receive {gross_amount * 0.90:.2f} after 10% fee)\n\n"
            "Please verify the transaction on the exchange.\n\n"
          
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

async def notify_admin_withdrawal(context: ContextTypes.DEFAULT_TYPE, admin_id: int, user_id: int, amount: float, address: str, tx_id:str):
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
                    InlineKeyboardButton("✅ Approve", callback_data=f"approve_withdraw_{user_id}_{amount}_{tx_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_withdraw_{user_id}_{amount}_{tx_id}")
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
            # Check if already processed (using message caption as indicator)
        if "✅ Verified" in query.message.caption or "❌ Rejected" in query.message.caption:
            await query.answer("⏳ This transaction was already processed", show_alert=True)
            return

        # Parse callback data with proper type conversion
        parts = query.data.split('_')
        action = str(parts[0])
        request_type = str(parts[1])
        user_id = int(parts[2])
        amount = float(parts[3])
        tx_id = str(parts[4]) if len(parts) > 4 else "UNKNOWN"
        user = await context.bot.get_chat(user_id)

        # Immediately disable the buttons to prevent duplicate clicks
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except:
            pass  # Fail silently if edit fails

        logger.info(f"Processing {action} for {request_type} of {amount} by user {user_id}")

        if request_type == "deposit":
            if action == "verify":

                try:
                    gross_amount = amount
                    net_amount = gross_amount * 0.90
                    
                    # Process deposit
                    if not account_manager.process_deposit(user_id, gross_amount):  # Store net amount after fee
                        await query.edit_message_text("❌ Failed to process deposit")
                        return
                    
                    account = account_manager.get_account_info(user_id)
                    # if account and account.get("first_deposit") == "1":  # Just became first deposit
                    referrer_id = account.get("referrer_id")
                    if referrer_id:
                            # Calculate and add referral bonus
                          
                            account_manager.add_referral_earning(referrer_id, gross_amount)
                             # Notify referrer
                            try:
                                await context.bot.send_message(
                                    chat_id=referrer_id,
                                    text=f"🎉 You earned {gross_amount*0.02:.2f} USDT referral bonus!"
                                )
                            except Exception as e:
                                logger.error(f"Failed to notify referrer: {e}")

                     # Log transaction
                    tx_logger.update_status(
                                tx_id=tx_id,
                                status="COMPLETED",
                                notes=f"Approved by @{query.from_user.username}"
                        )


                    # Notify admin
                    try:
                        await query.edit_message_caption(
                            caption=f"✅ Verified deposit of {gross_amount} USDT (credited {net_amount:.2f} after fee) for user{user.username if user.username else user.full_name} ",
                            reply_markup=InlineKeyboardMarkup([])  
                            )
                    except Exception as e:
                        logger.error(f"Failed to edit message caption: {e}")
                        await query.edit_message_text(
                            text=f"✅ Verified deposit of {gross_amount} USDT (credited {net_amount:.2f} after fee) for user @{user.username if user.username else user.full_name}",
                            reply_markup=InlineKeyboardMarkup([])
                        )
                        return    
                    # Notify user
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"✅ Your deposit has been approved\n\n"
                            f"Amount: {gross_amount:.2f} USDT\n"
                            f"Credited: {net_amount:.2f} USDT (after 10% fee)\n"
                            f"New Balance: {account_manager.get_balance(user_id):.2f} USDT"
                        )
                    )

                except Exception as e:
                    logger.error(f"Deposit approval error: {e}")
                    await query.answer("❌ Error approving deposit", show_alert=True)

            elif action == "reject":

                
                try:
                    # Log rejection
                    tx_logger.update_status(
                            tx_id=tx_id,
                            status="REJECTED",
                            notes=f"Rejected by @{query.from_user.username}"
                    )


                        # Notify admin
                    await query.edit_message_caption(f"❌ Rejected deposit of {amount} USDT")
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"⚠️ Your deposit of {amount} USDT was rejected"
                    )

                except Exception as e:
                    logger.error(f"Deposit rejection error: {e}")
                    await query.edit_message_text("❌ Error rejecting deposit")

        elif request_type == "withdraw":
            address = parts[4] if len(parts) > 4 else "UNKNOWN"  # Address is now parts[5]
                
            if action == "approve":

                try:
                        # Verify ROI status
                    # if not check_roi_status(user_id):
                    #     account = account_manager.get_account_info(user_id)
                    #     total_deposits = float(account.get("first_deposit", 0))
                    #     total_profits = float(account.get("total_interest", 0))
                    #     net_balance = float(account["balance"]) - total_profits

                    #     if net_balance < total_deposits:
                    #         await query.edit_message_text(
                    #             "❌ Cannot approve - ROI not reached\n"
                    #             f"Deposits: {total_deposits:.2f}\n"
                    #             f"Profits: {total_profits:.2f}"
                    #             )
                    #         return

                        # Process withdrawal
                    if not account_manager.update_balance(user_id, -amount):
                        await query.edit_message_text("❌ Failed to process withdrawal")
                        return

                    if not account_manager.update_total_withdrawals(user_id, amount):
                        logger.warning(f"Failed to update withdrawals for {user_id}")

                        # Log transaction
                    tx_logger.update_status(
                            tx_id=tx_id,
                            status="COMPLETED",
                            notes=f"Approved by @{query.from_user.username}"
                    )

                    withdrawal_tracker.record_withdrawal(user_id)

                        # Notify admin
                    await query.edit_message_text(
                            f"✅ Approved withdrawal of {amount} USDT for user @{user.username if user.username else user.full_name}\n"
                            f"to address: {address}"
                    )

                        # Notify user
                    await context.bot.send_message(
                            chat_id=user_id,
                            text=f"✅ Your withdrawal of {amount} USDT has been approved!\n"
                                f"Funds will be sent to: {address} in 2-3 hours.\n" 
                    )

                except Exception as e:
                    logger.error(f"Withdrawal approval error: {e}")
                    await query.edit_message_text("❌ Error approving withdrawal")

            elif action == "reject":
                try:
                        # Log rejection
                    tx_logger.update_status(
                            tx_id=tx_id,
                            status="Rejected",
                            notes=f"Rejected by @{query.from_user.username}"
                    )

                        # Notify admin
                    await query.edit_message_text(
                            
                            f"❌ Withdrawal Rejected\n"
                            f"User: {user_id}\n"
                            f"Amount: {amount:.2f} USDT\n"
                            f"By: @{query.from_user.username}"
                    )

                        # Notify user
                    await context.bot.send_message(
                            chat_id=user_id,
                            text=f"⚠️ Your withdrawal of {amount} USDT was rejected\n"
                                "Please contact support if this was unexpected."
                        )

                except Exception as e:
                    logger.error(f"Withdrawal rejection error: {e}")
                    await query.edit_message_text("❌ Error rejecting withdrawal")

    except Exception as e:
        logger.error(f"Verification error: {e}")
        await query.edit_message_text("❌ Error processing request")


# Deposit Handler
async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
   
    try:
        

        amount = float(update.message.text)
        user_id = str(update.effective_user.id)
        net_amount = round(amount * 0.90, 2)
        tx_id=str(uuid.uuid4())[:8]
        

        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive")
            return DEPOSIT_AMOUNT

        if amount < 100:
            await update.message.reply_text("❌ Minimum deposit is 100 USDT.")
            return DEPOSIT_AMOUNT

    
           # Store pending deposit
        context.user_data['deposit_data'] = {
                'gross_amount': amount,
                'net_amount': net_amount,
                'user_id': user_id,
                'tx_id': tx_id,  
            }

        tx_logger.log_trade(
            user_id=user_id,
            tx_type="DEPOSIT",
            amount=amount,
            tx_id=tx_id,
            notes=f"Pending deposit from user {user_id}"
        )

        await update.message.reply_text(
                f"*To deposit funds, send at least* `{amount} USDT`* (TRC-20),(BEP20),(USDCBEP20) *to your preferred address below and take a screenshot\n\n"
                "*Exchange Addresses \n\n* " 
                f"**USDT TRC20:** `{WALLETS['USDT_TRC20']}`\n\n"
                f"**USDT BEP20:** `{WALLETS['USDT_BEP20']}`\n\n"
                f"**USDC BEP20:** `{WALLETS['USDC_BEP20']}`\n\n"
                "After sending, please come back to the bot and upload the transaction screenshot.\n\n"
                f"_Note: A 10% deposit fee will be applied. Your credited balance will be {net_amount} USDT_",
                parse_mode='Markdown'
        )

        #   # Apply referral bonus if first deposit
        # account = account_manager.get_account_info(user_id)
        # if account and account.get("first_deposit") == "0":
        #     # Apply referral bonus
        #     referrer_id = account.get("referrer_id")
        #     if referrer_id:
        #         account_manager.add_referral_earning(referrer_id, amount)
        
            # Mark first deposit
        accounts = account_manager._load_accounts()
        for acc in accounts:
                if acc["telegram_id"] == str(user_id):
                 acc["first_deposit"] = "1"
                 acc["first_deposit_date"] = datetime.now().strftime("%Y-%m-%d")
                 acc["first_deposit_amount"] = str(amount)
                #  acc["total_deposits"] = str(float(acc.get("total_deposits", 0)) + amount)
                 account_manager._save_accounts(accounts)
                 break

        return TXN_PROOF 

   
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
    return DEPOSIT_AMOUNT

async def handle_transaction_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if we have deposit data
    if 'deposit_data' not in context.user_data:
        await update.message.reply_text("❌ Deposit information missing. Please start over.")
        return ConversationHandler.END
    
    deposit_data = context.user_data['deposit_data']
    user = update.effective_user
    
    if not update.message.photo:
        await update.message.reply_text("❌ Please send a screenshot of your transaction.")
        return TXN_PROOF
    
    try:
        # Get the highest resolution photo
        photo_file = await update.message.photo[-1].get_file()
        txn_details = update.message.caption or "No details provided"
        
        # Notify all admins
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=photo_file.file_id,
                    caption=(
                        f"⚠️ Deposit Verification Needed\n\n"
                        f"👤 User: {user.full_name} (@{user.username or 'N/A'})\n"
                        f"🆔 ID: {deposit_data['user_id']}\n"
                        f"💰 Amount: {deposit_data['gross_amount']} USDT\n"
                        f"💸 After fee: {deposit_data['net_amount']:.2f} USDT\n\n"
                        f"📝 Transaction Details:\n{txn_details}\n\n"
                        f"📅 Submitted: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "✅ Approve", 
                                callback_data=f"verify_deposit_{deposit_data['user_id']}_{deposit_data['gross_amount']}_{deposit_data['tx_id']}"
                            ),
                            InlineKeyboardButton(
                                "❌ Reject", 
                                callback_data=f"reject_deposit_{deposit_data['user_id']}_{deposit_data['gross_amount']}_{deposit_data['tx_id']}"
                            )
                        ]
                    ])
                )
            except Exception as e:
                logger.error(f"Error notifying admin {admin_id}: {e}")

        await update.message.reply_text(
            "✅ Your deposit proof has been submitted for admin review.\n"
            "You'll receive a notification once processed.",
            reply_markup=main_menu_keyboard()
        )
        
        # Clean up the context
        del context.user_data['deposit_data']
        
    except Exception as e:
        logger.error(f"Error handling transaction proof: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")
    
    return ConversationHandler.END


# Withdraw Handlers
async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        user_id = str(update.effective_user.id)
        balance = account_manager.get_balance(user_id)  


              # Check minimum withdrawal
        # if amount < MIN_WITHDRAWAL:
        #     await update.message.reply_text(f"❌ Minimum withdrawal is {MIN_WITHDRAWAL} USDT.")
        #     return WITHDRAW_AMOUNT
        
        # Check account balance
        balance = account_manager.get_balance(user_id)
        if amount > balance:
            await update.message.reply_text("❌ Insufficient balance.")
            return WITHDRAW_AMOUNT
        
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive")
            return WITHDRAW_AMOUNT

        if amount < 10:
            await update.message.reply_text("❌ Minimum withdrawal is 10 USDT.")
            return WITHDRAW_AMOUNT
        
          # Check withdrawal limits
        if not withdrawal_tracker.can_withdraw(user_id):
            next_withdrawal = (datetime.now() + WITHDRAWAL_COOLDOWN).strftime("%Y-%m-%d")
            await update.message.reply_text(
                f"❌ You've reached your monthly withdrawal limit.\n"
                f"Next available withdrawal: {next_withdrawal}"
            )
            return ConversationHandler.END
        
         # Check if withdrawing profits only
        account_info = account_manager.get_account_info(user_id)
        if not account_info:
            await update.message.reply_text("❌ Account not found")
            return ConversationHandler
        
        total_deposits = float(account_info.get("total_deposits", 0))
        total_profits = float(account_info.get("total_interest", 0))
        current_balance = float(account_info["balance"])
    

        if total_deposits == 0 and current_balance > 0:
            await update.message.reply_text(
                    "❌ Withdrawal blocked: Account anomality detected.\n"
                    "Please contact support to verify your balance."
                )
            return WITHDRAW_AMOUNT

        # if not check_roi_status(user_id):
        #     principal_remaining = max(0, total_deposits - total_profits)
        #     available_to_withdraw = max(0, current_balance - principal_remaining)
            
        #     if amount > available_to_withdraw:
        #         await update.message.reply_text(
        #             f"❌ Can only withdraw {available_to_withdraw:.2f} USDT (profits) but you haven't achieved your ROI \n"
        #             f"• Deposited: {total_deposits:.2f}\n"
        #             f"• Profits earned: {total_profits:.2f}"
        #         )
        #         return WITHDRAW_AMOUNT

    # Record the withdrawal attempt
                 
        net_amount = round(amount * 0.90, 2)
        context.user_data['withdraw_amount'] = amount
        context.user_data['withdraw_net_amount'] = net_amount



        await update.message.reply_text(
            f"✅ Withdrawal request accepted.\n"
            f"You will receive {net_amount} USDT after a 10% fee.\n\n"
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
    net_amount = amount * 0.90
    tx_id=str(uuid.uuid4())[:8]

    if not amount:
        await update.message.reply_text("❌ Withdrawal process error. Please start over.")
        return ConversationHandler.END
    
 
    tx_logger.log_trade(
        user_id=user_id,
        tx_type="WITHDRAW",
        tx_id=tx_id,
        amount=amount,
        address=address,
        notes=f"Pending withdraw from user {user_id}"
    )

    # Store withdrawal request
    context.user_data['withdraw_address'] = address
    
    # Notify admin for approval
    for admin_id in ADMIN_IDS:
        await notify_admin_withdrawal(context, admin_id, user_id, amount, address,tx_id)
    
    await update.message.reply_text(
        f"⌛ Your withdrawal request of {amount:.2f} USDT (you'll receive {net_amount:.2f} USDT after fees) "
        "has been submitted for admin approval.\n"
        "You'll receive a notification once processed.",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END



async def calculate_and_distribute_profits(context: ContextTypes.DEFAULT_TYPE = None):
    try:
        # Connect to MT4 EA
        mt4 = EACommunicator_API()
        mt4.Connect()

        # Get closed positions and filter out deposits
        closed_positions = mt4.Get_all_closed_positions()
        
        if closed_positions is None or closed_positions.empty:
            logger.info("No closed positions found")
            return False
            
        # Get already processed trades
        processed_trades = account_manager.get_processed_trades()
        
        # Filter out deposits plus withdraws and already processed trades
        valid_trades = closed_positions[
            (closed_positions['symbol'].notna()) &
            (closed_positions['position_type'].isin(['buy', 'sell'])) &  # Only buy/sell trades
            (~closed_positions['ticket'].isin(processed_trades)) &
            (~closed_positions['comment'].str.contains("deposit|withdraw|balance|adjust|transfer|funding", case=False, na=False))
        ]


        
        if valid_trades.empty:
            logger.info("No new valid trades to process")
            return False

        total_closed_pl = round(valid_trades['profit'].sum(), 2)
        logger.info(f"New Valid Closed P/L: {total_closed_pl} from {len(valid_trades)} trades")

        # Skip if no significant movement
        if abs(total_closed_pl) < 1:
            logger.info("No significant realized P/L to apply.")
            return False

        # Load all user accounts
        accounts = account_manager._load_accounts()
        total_user_balances = sum(float(acc["balance"]) for acc in accounts)

        if total_user_balances == 0:
            logger.warning("No user balances to apply P/L to.")
            return False

        updated = False
        for acc in accounts:
            user_balance = float(acc["balance"])
            if user_balance > 0:
                user_share = (user_balance / total_user_balances) * total_closed_pl
                acc["balance"] = f"{user_balance + user_share:.2f}"
                current_interest = float(acc.get("total_interest", 0))
                acc["total_interest"] = f"{current_interest + user_share:.2f}"
                acc["last_profit_date"] = datetime.now().strftime("%Y-%m-%d")
                updated = True

        if updated:
            # Save account updates
            if not account_manager._save_accounts(accounts):
                logger.error("Failed to save updated user balances.")
                return False
            
            # Mark these trades as processed
            new_processed_trades = processed_trades.union(set(valid_trades['ticket'].tolist()))
            account_manager.save_processed_trades(new_processed_trades)
            
            logger.info(f"Distributed {total_closed_pl:.2f} from {len(valid_trades)} new trades")

            if context:
                notification_text = (
                    f"{'✅ Profit' if total_closed_pl > 0 else '⚠️ Loss'} Distribution Complete\n\n"
                    f"• New Trades Processed: {len(valid_trades)}\n"
                    f"• Closed P/L: {total_closed_pl:.2f}\n"
                    f"• Action: {'Distributed' if total_closed_pl > 0 else 'Deducted'}"
                )
                
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=notification_text
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify admin {admin_id}: {e}")

            return True

        return False
    except Exception as e:
        logger.error(f"Error in profit distribution: {str(e)}")
        return False

async def force_profit_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    success = await calculate_and_distribute_profits(context)
    await update.message.reply_text(
        "✅ Manual profit run completed" if success else "❌ Profit run failed"
    )
   
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




async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if hasattr(update, 'callback_query') and update.callback_query:
        # Handle callback query case
        user_id = update.callback_query.from_user.id
        message = update.callback_query.message
        is_callback = True
    else:
        # Handle regular message case
        user_id = update.effective_user.id
        message = update.message
        is_callback = False

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
        "_Earn 2% of your referrals' deposits_"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            message,
            parse_mode='MarkdownV2',
            reply_markup=main_menu_keyboard()
        )

    else:   
        await update.message.reply_text(
            message,
            parse_mode='MarkdownV2',
            reply_markup=main_menu_keyboard()
        )

async def handle_referral_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref_id = None

    
    # Extract referral ID from deep link (full match to what's stored in CSV)
    if context.args and context.args[0].startswith('ref_'):
        ref_id = context.args[0][4:].strip()  # remove "ref_" and spaces

    # Prevent self-referrals
    if ref_id:
        referrer_telegram_id = account_manager._get_telegram_id_from_referral_id(ref_id)
        if referrer_telegram_id == str(user.id):
            ref_id = None  # ignore if user tries their own link

    # Create account with referral 
    success, referrer_telegram_id = account_manager.add_user_if_not_exists(user.id, "main", str(user.id), referral_id=ref_id)

    # Send welcome/start message
    await start(update, context)

    # Notify referrer 
    if success and referrer_telegram_id:
        try:
            await context.bot.send_message(
                chat_id=referrer_telegram_id,
                text=f"🎉 New referral! @{user.username or 'A user'} joined using your link"
            )
        except Exception as e:
            logger.error(f"Failed to notify referrer {referrer_telegram_id}: {e}")
                

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


# Main
def main():
    app = Application.builder().token(TOKEN).build()
    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        calculate_and_distribute_profits,
        'interval',
        seconds=30,  
      
        timezone='UTC'
    )

 
    async def on_startup(app):
        scheduler.start()

    app.add_handler(CommandHandler('start', handle_referral_start))
    # app.add_handler(CommandHandler("testnotify", test_notify))
    # app.add_handler(CommandHandler("amIadmin", check_admin))
    app.add_handler(CallbackQueryHandler(
        handle_admin_verification, 
        pattern=r"^(approve|reject|verify)_(withdraw|deposit)_\d+_\d+(\.\d+)?(_\w+)?$"
    ))
    app.add_handler(CommandHandler("admin", admin_menu))
    # app.add_handler(CommandHandler('deposit', start_deposit_flow))
    # app.add_handler(CommandHandler('withdraw', start_withdraw_flow))
    app.add_handler(CommandHandler('account', show_account))
    app.add_handler(CommandHandler('help', show_help))
    app.add_handler(CommandHandler('referral', referral_command))
    app.add_handler(CommandHandler('wallets', show_wallets))
    app.add_handler(CommandHandler('faqs', faq_command))
    app.add_handler(CommandHandler('community', community_command))
    app.add_handler(CommandHandler('reconcile', reconcile_command))
    app.add_handler(CommandHandler('runprofits', force_profit_run))
    app.add_handler(CommandHandler('tradingstats',trading_stats))
    app.add_handler(CommandHandler('history',transaction_history))
 
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start),
                       CommandHandler('deposit', start_deposit_flow),  
                       CommandHandler('withdraw', start_withdraw_flow),                 
                       CallbackQueryHandler(handle_menu)],
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            TXN_PROOF: [
                MessageHandler(filters.PHOTO, handle_transaction_proof),
                MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("Please send a screenshot of your transaction"))
            ],          
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_address)],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('faqs', faq_command),  
            CommandHandler('community', community_command),
            CallbackQueryHandler(handle_menu, pattern='^main_menu$')
        ],
        allow_reentry=True
    )

    edit_balance_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(edit_user_balance, pattern=r'^edit_user_\d+$')],
            states={
                EDIT_USER_BALANCE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, process_new_balance),
                    CallbackQueryHandler(cancel_edit, pattern=r'^cancel_edit$')
                ]
            },
            fallbacks=[
                CallbackQueryHandler(cancel_edit, pattern=r'^cancel_edit$'),
                CallbackQueryHandler(handle_page_change, pattern=r'^(prev_page|next_page)$'),
                CallbackQueryHandler(list_all_users, pattern=r'^admin_menu$')
            ],
            allow_reentry=True
        )
    
    app.add_handler(edit_balance_conv)
    app.add_handler(CallbackQueryHandler(handle_page_change, pattern=r'^(prev_page|next_page)$'))
    app.add_handler(CallbackQueryHandler(list_all_users, pattern=r'^admin_edit_balance$'))
    app.add_handler(CallbackQueryHandler(trading_stats, pattern='^tradingstats$'))


    app.add_handler(conv_handler)
    app.post_init = on_startup


    print("Bot is running...\nPolling for updates...")
    app.run_polling()

if __name__ == '__main__':
    main()