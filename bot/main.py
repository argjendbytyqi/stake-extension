import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initial greeting with action buttons."""
    keyboard = [
        [InlineKeyboardButton("Buy StakePeek Blitz 🚀", callback_data="buy_now")],
        [InlineKeyboardButton("How to Use", callback_data="how_to")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚽ **Drogba Bot: StakePeek Blitz Edition**\n\n"
        "Welcome Argjend. High-speed license delivery system initialized.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle interaction with inline buttons."""
    query = update.callback_query
    await query.answer()

    if query.data == "buy_now":
        # Placeholder for NOWPayments API call
        await query.edit_message_text(
            text="Payment system integration in progress...\n\nNext step: Connecting NOWPayments API.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back")]])
        )
    
    elif query.data == "how_to":
        await query.edit_message_text(
            text="**Quick Guide:**\n1. Buy License\n2. Download ZIP\n3. Install in Chrome\n4. Win.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back")]]),
            parse_mode="Markdown"
        )
    
    elif query.data == "back":
        await start(update, context) # Simple loop back

def main():
    if not TOKEN or "your_token" in TOKEN:
        print("Error: Set TELEGRAM_BOT_TOKEN in bot/.env")
        return

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("⚽ Drogba Bot is standing by...")
    app.run_polling()

if __name__ == "__main__":
    main()
