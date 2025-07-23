import os
from typing import Final
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.error import BadRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from account_manager import AccountManager 
from datetime import datetime, timedelta

from trade_reconciler import TransactionLogger
import re
import pandas as pd
from pathlib import Path

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
# TOKEN ='7759076862:AAHPJrG22OFySb3cGhrPkNM8I7lfwxvm8Rk'
TOKEN = '7603656998:AAHYKMQN9UQLfZ9Dm_Z3RxgSyIMgZvQdNes'
BOT_USERNAME: Final = os.getenv('BOT_USERNAME')
COMMUNITY_LINK = "https://t.me/Unclesbotsupport"
ADMIN_IDS = [5079683472,5823817060]  
DEPOSIT_AMOUNT, WITHDRAW_AMOUNT, WITHDRAW_ADDRESS, TXN_PROOF = range(4)
REFERRAL_BONUS_PERCENT=10
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
'USDT_TRC20':'TEchKQ7McbzhxR9BUUrssCRjK5jJsLaF2V',
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
    equity = account_manager.get_current_equity(user_id)
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
        f"🔒 WITHDRAW STATUS: `{'Unlocked' if check_roi_status(user_id) else 'Locked'}`\n\n"
        f"💸 TOTAL WITHDRAWS: `{total_withdrawals} USD`\n\n"
        f"📅 LAST WITHDRAW: `{last_withdrawal}`\n\n"
        f"🔄 WITHDRAWS THIS MONTH: `{withdrawals_this_month}/{MAX_WITHDRAWALS_PER_MONTH}`\n\n"      
        # f"🔗 REFERRAL ID `{referral_id}`\n\n"
        "_Note: All deposits and withdrawals include a 10% fee._\n\n"
    )
    

       # Connect to MT4 and get live balance   
    mt4 =  EACommunicator_API

    def get_mt4_equity():
        """Gets current account equity (balance + floating P/L)"""
        mt4 = EACommunicator_API()
        try:
            mt4.Connect()
            return mt4.Get_current_equity()  # Uses your existing method
        except Exception as e:
            logger.error(f"MT4 equity check failed: {str(e)}")
            raise
        finally:
            mt4.Disconnect()    
    try:
        mt4_balance = get_mt4_equity()
        response += f"\n🔹 COLLECTIVE POOL: *{mt4_balance:.2f} USD*"
    except Exception as e:
        logger.error(f"Failed to get MT4 balance: {e}")
        response += "\n🔹 MT4 Balance: Unavailable"


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
        formatted_amount = f"{float(gross_amount):.2f}"
        tx_hash = context.user_data.get("tx_", "N/A")
        
        with open("pending_deposits.csv", "a") as f:
            f.write(f"{user_id},{gross_amount},{tx_hash},{datetime.now()}\n")

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Verify Deposit", callback_data=f"verify_deposit_{user_id}_{formatted_amount}")],
            [InlineKeyboardButton("❌ Reject Deposit", callback_data=f"reject_deposit_{user_id}_{formatted_amount}")]
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

        # Parse callback data with proper type conversion
        parts = query.data.split('_')
        action = str(parts[0])
        request_type = str(parts[1])
        user_id = int(parts[2])
        amount = float(parts[3])
        tx_id = str(parts[4]) if len(parts) > 4 else "UNKNOWN"

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

                    # Update transaction log
                    tx_logger.update_status(
                        tx_id=tx_id,
                        status="COMPLETED",
                        notes=f"Approved by @{query.from_user.username}"
                    )

                    # Notify admin
                    await query.edit_message_caption(
                        caption=f"✅ Verified deposit of {gross_amount} USDT (credited {net_amount:.2f} after fee)",
                        reply_markup=InlineKeyboardMarkup([])  
                        )
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
                    if not check_roi_status(user_id):
                        account = account_manager.get_account_info(user_id)
                        total_deposits = float(account.get("first_deposit", 0))
                        total_profits = float(account.get("total_interest", 0))
                        net_balance = float(account["balance"]) - total_profits

                        if net_balance < total_deposits:
                            await query.edit_message_text(
                                "❌ Cannot approve - ROI not reached\n"
                                f"Deposits: {total_deposits:.2f}\n"
                                f"Profits: {total_profits:.2f}"
                                )
                            return

                        # Process withdrawal
                    if not account_manager.update_balance(user_id, -amount):
                        await query.edit_message_text("❌ Failed to process withdrawal")
                        return

                    if not account_manager.update_total_withdrawals(user_id, amount):
                        logger.warning(f"Failed to update withdrawals for {user_id}")

                        # Log transaction
                    tx_logger.log_trade(
                            tx_id=tx_id,
                            user_id=user_id,
                            tx_type="Withdrawal",
                            amount=-amount,
                            notes=f"Approved by @{query.from_user.username}"
                    )

                    withdrawal_tracker.record_withdrawal(user_id)

                        # Notify admin
                    await query.edit_message_text(
                            f"✅ Approved withdrawal of {amount} USDT\n"
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
                    tx_logger.log_trade(
                            tx_id=tx_id,
                            user_id=user_id,
                            tx_type="Withdrawal_Rejected",
                            amount=0,
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

        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive")
            return DEPOSIT_AMOUNT

        if amount < 100:
            await update.message.reply_text("❌ Minimum deposit is 100 USDT.")
            return DEPOSIT_AMOUNT

        import uuid
           # Store pending deposit
        context.user_data['deposit_data'] = {
                'gross_amount': amount,
                'net_amount': net_amount,
                'user_id': user_id,
                'tx_id': str(uuid.uuid4())[:8],  # Generate a unique transaction ID
            }

        
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
        if amount < MIN_WITHDRAWAL:
            await update.message.reply_text(f"❌ Minimum withdrawal is {MIN_WITHDRAWAL} USDT.")
            return WITHDRAW_AMOUNT
        
        # Check account balance
        balance = account_manager.get_balance(user_id)
        if amount > balance:
            await update.message.reply_text("❌ Insufficient balance.")
            return WITHDRAW_AMOUNT
        
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive")
            return WITHDRAW_AMOUNT

        if amount < 50:
            await update.message.reply_text("❌ Minimum withdrawal is 50 USDT.")
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

        if not check_roi_status(user_id):
            principal_remaining = max(0, total_deposits - total_profits)
            available_to_withdraw = max(0, current_balance - principal_remaining)
            
            if amount > available_to_withdraw:
                await update.message.reply_text(
                    f"❌ Can only withdraw {available_to_withdraw:.2f} USDT (profits) but you haven't achieved your ROI \n"
                    f"• Deposited: {total_deposits:.2f}\n"
                    f"• Profits earned: {total_profits:.2f}"
                )
                return WITHDRAW_AMOUNT

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

    if not amount:
        await update.message.reply_text("❌ Withdrawal process error. Please start over.")
        return ConversationHandler.END
    

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
        
        # Filter out deposits and already processed trades
        valid_trades = closed_positions[
            ~((closed_positions['symbol'].isna()) & (closed_positions['profit'] > 0)) &
            (~closed_positions['ticket'].isin(processed_trades))
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
    app.add_handler(CommandHandler('stats', stats_command))
    app.add_handler(CommandHandler('referral', referral_command))
    app.add_handler(CommandHandler('wallets', show_wallets))
    app.add_handler(CommandHandler('faqs', faq_command))
    app.add_handler(CommandHandler('community', community_command))
    app.add_handler(CommandHandler('reconcile', reconcile_command))
    app.add_handler(CommandHandler('runprofits', force_profit_run))
 
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
    app.add_handler(conv_handler)
    app.post_init = on_startup


    print("Bot is running...\nPolling for updates...")
    app.run_polling()

if __name__ == '__main__':
    main()
