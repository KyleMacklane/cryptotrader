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