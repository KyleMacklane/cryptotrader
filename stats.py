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

    # Check if user already exists
    existing_account = account_manager.get_account_info(user.id)
    if existing_account:
        # Existing user - show welcome back message
        welcome_msg = f"👋 Welcome back, {user.first_name}!\n\nGood to see you again! Access your account below:"
        
        # If they came via referral link but already exist, still acknowledge the referrer
        if ref_id and referrer_telegram_id and referrer_telegram_id != str(user.id):
            welcome_msg += f"\n\n📨 Thank you for sharing your referral link!"
        
        await update.message.reply_text(welcome_msg, reply_markup=main_menu_keyboard())
        return

    # Check if user is pending approval
    if account_manager._is_user_pending(user.id):
        pending_msg = (
            "⏳ Your registration is pending admin approval.\n\n"
            "Please wait while we review your application. "
            "You'll receive a notification once approved."
        )
        
        # Include referral info if applicable
        if ref_id:
            pending_msg += f"\n\n📨 Referral code: {ref_id}"
            
        await update.message.reply_text(
            pending_msg,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Check Status", callback_data="check_approval_status")]
            ])
        )
        return

    # New user - add to pending and notify admin
    result = account_manager.add_pending_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        referral_id=ref_id
    )

    if result == "added":
        # Build admin notification message with referral info
        admin_message = (
            "🆕 New User Registration\n\n"
            f"👤 User: {user.full_name}\n"
            f"📱 Username: @{user.username or 'N/A'}\n"
            f"🆔 ID: {user.id}\n"
            f"📅 Registered: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        )
        
        if ref_id:
            referrer_info = ""
            referrer_telegram_id = account_manager._get_telegram_id_from_referral_id(ref_id)
            if referrer_telegram_id:
                referrer_account = account_manager.get_account_info(referrer_telegram_id)
                if referrer_account:
                    referrer_name = f"{referrer_account.get('first_name', '')} {referrer_account.get('last_name', '')}".strip()
                    referrer_username = referrer_account.get('username', '')
                    referrer_info = f"\n👥 Referred by: {referrer_name} (@{referrer_username or 'N/A'}) - ID: {referrer_telegram_id}"
            
            admin_message += f"🔗 Referral Code: {ref_id}{referrer_info}"
        else:
            admin_message += "🔗 Referral: None (Organic registration)"

        # Notify admins
        for admin_id in ADMIN_IDS:
            try:
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Approve", callback_data=f"approve_user_{user.id}"),
                        InlineKeyboardButton("❌ Reject", callback_data=f"reject_user_{user.id}")
                    ]
                ])
                
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_message,
                    reply_markup=keyboard
                )
            except Exception as e:
                logger.error(f"Error notifying admin {admin_id}: {e}")

        # Send waiting message to user
        user_message = (
            "📝 Thank you for your interest!\n\n"
            "Your registration has been submitted for admin approval. "
            "This usually takes a few minutes to a few hours.\n\n"
        )
        
        if ref_id:
            user_message += "📨 Your referral code has been recorded and will be applied upon approval.\n\n"
            
        user_message += "You'll receive a notification once your account is approved."

        await update.message.reply_text(
            user_message,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Check Approval Status", callback_data="check_approval_status")],
                [InlineKeyboardButton("📞 Contact Support", url="https://t.me/Unclesbotsupport")]
            ])
        )
        
    elif result == "pending":
        await update.message.reply_text(
            "⏳ Your registration is already pending approval.\n\n"
            "Please wait while we review your application.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Check Status", callback_data="check_approval_status")]
            ])
        )
    else:
        await update.message.reply_text(
            "❌ An error occurred during registration.\n\n"
            "Please try again or contact support if the issue persists.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📞 Contact Support", url="https://t.me/Unclesbotsupport")]
            ])
        )

async def handle_user_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin approval/rejection of new users"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ Admin privileges required")
        return

    try:
        action, user_id = query.data.split('_')[0], int(query.data.split('_')[2])
        
        if action == "approve":
            # Approve the user
            if account_manager.approve_user(user_id, query.from_user.id):
                # Notify user
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "🎉 Your account has been approved!\n\n"
                            "Welcome to Uncle Hard Scalping Bot! "
                            "You can now access all features and start investing.\n\n"
                            "Use the menu below to get started:"
                        ),
                        reply_markup=main_menu_keyboard()
                    )
                except Exception as e:
                    logger.error(f"Error notifying approved user: {e}")

                # Update admin message
                await query.edit_message_text(
                    f"✅ User {user_id} approved successfully!\n\n"
                    "They have been notified and can now access the bot.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📊 View User", callback_data=f"view_user_{user_id}")]
                    ])
                )
            else:
                await query.edit_message_text("❌ Failed to approve user")
                
        elif action == "reject":
            # Reject the user
            if account_manager.reject_user(user_id, query.from_user.id):
                # Notify user
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "❌ Your registration has been declined.\n\n"
                            "If you believe this is an error, please contact support."
                        )
                    )
                except Exception as e:
                    logger.error(f"Error notifying rejected user: {e}")

                await query.edit_message_text(f"❌ User {user_id} has been rejected")
            else:
                await query.edit_message_text("❌ Failed to reject user")
                
    except Exception as e:
        logger.error(f"Error handling user approval: {e}")
        await query.edit_message_text("❌ Error processing request")

async def check_approval_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Let users check their approval status"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Check if approved
    if account_manager.get_account_info(user_id):
        await query.edit_message_text(
            "✅ Your account is approved and active!\n\n"
            "You can now access all features:",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Check if pending
    if account_manager._is_user_pending(user_id):
        await query.answer("⏳ Your application is still under review", show_alert=True)
        return
    
    # Not registered
    await query.edit_message_text(
        "❌ You haven't registered yet.\n\n"
        "Please use the /start command to begin registration.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Start Registration", callback_data="start_registration")]
        ])
    )    

async def view_pending_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to view all pending users"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    pending_users = account_manager.get_pending_users()
    
    if not pending_users:
        await update.message.reply_text("📭 No pending user registrations")
        return
    
    message = "🕐 Pending User Registrations:\n\n"
    for user in pending_users:
        # Get referrer info if available
        referrer_info = ""
        if user.get('referral_id'):
            referrer_telegram_id = account_manager._get_telegram_id_from_referral_id(user['referral_id'])
            if referrer_telegram_id:
                referrer_account = account_manager.get_account_info(referrer_telegram_id)
                if referrer_account:
                    referrer_name = f"{referrer_account.get('first_name', '')} {referrer_account.get('last_name', '')}".strip()
                    referrer_info = f"\n   👥 Referrer: {referrer_name} (ID: {referrer_telegram_id})"
        
        message += (
            f"👤 {user['first_name']} {user['last_name']}\n"
            f"📱 @{user['username'] or 'N/A'}\n"
            f"🆔 {user['telegram_id']}\n"
            f"📅 {user['timestamp'][:16]}\n"
            f"🔗 Ref: {user['referral_id'] or 'None'}{referrer_info}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
    
    # Add action buttons
    keyboard = []
    for user in pending_users[:5]:  # Show first 5 users with action buttons
        keyboard.append([
            InlineKeyboardButton(f"✅ Approve {user['telegram_id']}", callback_data=f"approve_user_{user['telegram_id']}"),
            InlineKeyboardButton(f"❌ Reject {user['telegram_id']}", callback_data=f"reject_user_{user['telegram_id']}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="admin_view_pending")])
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )



