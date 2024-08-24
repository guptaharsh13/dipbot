import os
import logging
from datetime import datetime, timedelta
import yfinance as yf
import re
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv
import pytz

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Chat ID to send notifications
NOTIFICATION_CHAT_ID = os.getenv("NOTIFICATION_CHAT_ID")

# Stock symbols for Sensex and Nifty
SENSEX_SYMBOL = "^BSESN"
NIFTY_SYMBOL = "^NSEI"

# Alert thresholds and their corresponding emojis and prefixes
ALERT_LEVELS = [
    {
        "threshold": float(os.getenv("ALERT_THRESHOLD_1", "-0.01")),
        "emoji": "⚠️",
        "prefix": "ALERT",
    },
    {
        "threshold": float(os.getenv("ALERT_THRESHOLD_2", "-0.03")),
        "emoji": "🚨",
        "prefix": "WARNING",
    },
    {
        "threshold": float(os.getenv("ALERT_THRESHOLD_3", "-0.06")),
        "emoji": "🔥",
        "prefix": "CRITICAL",
    },
]

# Time interval for checking prices (in seconds)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))  # Default: 5 minutes

# Morning update time (24-hour format)
MORNING_UPDATE_TIME = os.getenv("MORNING_UPDATE_TIME", "09:15")

# Flag to control alert pausing
alerts_paused = False

# Timezone settings
IST = pytz.timezone('Asia/Kolkata')
UTC = pytz.UTC

def escape_markdown_v2(text):
    """Helper function to escape special characters for MarkdownV2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', str(text))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    welcome_message = (
        "🚀 *Welcome to the Refined Indian Stock Market Monitor Bot\\!*\n\n"
        "I'm here to keep you updated on the Sensex and Nifty indices\\. "
        "Here's what I can do for you:\n\n"
        "• Send regular price updates\n"
        "• Alert you about significant market movements\n"
        "• Provide daily morning updates\n\n"
        "To get started, try the /help command to see all available options\\."
    )
    await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN_V2)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a detailed help message when the command /help is issued."""
    help_text = (
        "📚 *Available Commands:*\n\n"
        "• /start \\- Initialize the bot and get a welcome message\n"
        "• /help \\- Display this help message\n"
        "• /check \\- Manually request current stock prices\n"
        "• /stop\\_alerts \\- Pause alerts until the next morning\n"
        "• /resume\\_alerts \\- Resume paused alerts\n"
        "• /status \\- Get the current bot configuration and status\n"
        "• /set\\_morning\\_time HH:MM \\- Set the morning update time\n\n"
        "ℹ️ The bot will automatically send alerts for significant market movements "
        "and provide a daily morning update at the configured time\\."
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)


async def stop_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pause alerts until next morning."""
    global alerts_paused
    alerts_paused = True
    response = (
        "🔕 *Alerts Paused*\n\n"
        "All alerts have been paused until the next morning update\\. "
        "You will still receive the daily morning update as scheduled\\.\n\n"
        "Use /resume\\_alerts to reactivate alerts at any time\\."
    )
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN_V2)

async def resume_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume alerts."""
    global alerts_paused
    alerts_paused = False
    response = (
        "🔔 *Alerts Resumed*\n\n"
        "Alert notifications have been reactivated\\. "
        "You will now receive alerts for significant market movements as they occur\\."
    )
    await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN_V2)

async def get_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get current bot status and configuration."""
    alert_thresholds = '  '.join([f"{t['emoji']} {escape_markdown_v2(f'{t['threshold']:.1%}')}" for t in ALERT_LEVELS])
    
    status_message = (
        "🤖 *Bot Status and Configuration*\n\n"
        f"• *Alerts:* {'🔕 Paused' if alerts_paused else '🔔 Active'}\n"
        f"• *Alert Thresholds:*\n  {alert_thresholds}\n"
        f"• *Check Interval:* Every {CHECK_INTERVAL // 60} minutes\n"
        f"• *Morning Update:* Scheduled at {MORNING_UPDATE_TIME}\n\n"
        "Use /help to see available commands\\."
    )
    await update.message.reply_text(status_message, parse_mode=ParseMode.MARKDOWN_V2)

def get_stock_data(symbol: str, days: int = 5):
    """Fetch stock data for the given symbol."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    data = yf.Ticker(symbol).history(start=start_date, end=end_date)
    return data

def calculate_price_change(data):
    """Calculate price change from the most recent data."""
    if len(data) < 2:
        return None, None, None
    current_price = data["Close"].iloc[-1]
    previous_close = data["Close"].iloc[-2]
    price_change = (current_price - previous_close) / previous_close
    return current_price, previous_close, price_change

async def check_prices(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check the current prices of Sensex and Nifty and send notifications based on alert thresholds."""
    global alerts_paused

    try:
        current_time = datetime.now(UTC)
        ist_time = utc_to_ist(current_time)
        
        sensex_data = get_stock_data(SENSEX_SYMBOL)
        nifty_data = get_stock_data(NIFTY_SYMBOL)

        sensex_current, sensex_previous, sensex_change = calculate_price_change(sensex_data)
        nifty_current, nifty_previous, nifty_change = calculate_price_change(nifty_data)

        logger.info(
            f"Sensex: Current: {sensex_current}, Previous: {sensex_previous}, Change: {sensex_change:.2%}"
        )
        logger.info(
            f"Nifty: Current: {nifty_current}, Previous: {nifty_previous}, Change: {nifty_change:.2%}"
        )

        if sensex_change is None or nifty_change is None:
            logger.warning("Insufficient data available. Skipping price check.")
            return

        # Check if it's time for the morning update
        if context.job.data.get('is_morning_update', False):
            await send_daily_status(
                context, sensex_current, nifty_current, sensex_change, nifty_change
            )
            alerts_paused = False  # Reset alerts_paused flag after morning update

        # Check against alert thresholds if alerts are not paused
        if not alerts_paused:
            await check_and_send_alert(
                context, "Sensex", sensex_current, sensex_previous, sensex_change
            )
            await check_and_send_alert(
                context, "Nifty", nifty_current, nifty_previous, nifty_change
            )

    except Exception as e:
        logger.error(f"Error checking prices: {e}")

async def check_and_send_alert(
    context: ContextTypes.DEFAULT_TYPE,
    index_name: str,
    current_price: float,
    previous_close: float,
    price_change: float,
) -> None:
    """Check if an alert should be sent and send it with the appropriate formatting."""
    for level in reversed(ALERT_LEVELS):
        threshold = level["threshold"]
        if (threshold > 0 and price_change >= threshold) or (threshold < 0 and price_change <= threshold):
            await send_alert(
                context, index_name, current_price, previous_close, price_change, level
            )
            break

async def send_alert(
    context: ContextTypes.DEFAULT_TYPE,
    index_name: str,
    current_price: float,
    previous_close: float,
    price_change: float,
    alert_level: dict,
) -> None:
    """Send an alert message for a specific index with improved formatting based on the alert level."""
    direction = "⬆️" if price_change > 0 else "⬇️"
    change_abs = abs(price_change)
    
    # Determine color based on direction
    color = "🟢" if price_change > 0 else "🔴"
    
    message = (
        f"{alert_level['emoji']} *{alert_level['prefix']}: {escape_markdown_v2(index_name)} {direction} {escape_markdown_v2(f'{change_abs:.2%}')}*\n\n"
        f"{color} *Current Price:* {escape_markdown_v2(f'{current_price:.2f}')}\n"
        f"📊 *Previous Close:* {escape_markdown_v2(f'{previous_close:.2f}')}\n"
        f"{direction} *Change:* {escape_markdown_v2(f'{price_change:+.2%}')} \\({escape_markdown_v2(f'{current_price - previous_close:+.2f}')}\\)\n\n"
        f"🎯 *Alert Threshold:* {escape_markdown_v2(f'{alert_level['threshold']:.1%}')}\n\n"
        "_Use /stop\\_alerts to pause notifications_"
    )
    logger.info(f"Sending {alert_level['prefix']} alert for {index_name}")
    await context.bot.send_message(chat_id=NOTIFICATION_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN_V2)

async def send_daily_status(
    context: ContextTypes.DEFAULT_TYPE,
    sensex_price: float,
    nifty_price: float,
    sensex_change: float,
    nifty_change: float,
) -> None:
    """Send daily morning status update with improved formatting."""
    sensex_emoji = "🟢" if sensex_change >= 0 else "🔴"
    nifty_emoji = "🟢" if nifty_change >= 0 else "🔴"
    
    ist_now = utc_to_ist(datetime.now(UTC))
    
    message = (
        f"🌅 *Daily Market Update* \\({escape_markdown_v2(ist_now.strftime('%Y-%m-%d %H:%M'))} IST\\)\n\n"
        f"{sensex_emoji} *Sensex:* {escape_markdown_v2(f'{sensex_price:.2f}')} \\({escape_markdown_v2(f'{sensex_change:+.2%}')}\\)\n"
        f"{nifty_emoji} *Nifty:* {escape_markdown_v2(f'{nifty_price:.2f}')} \\({escape_markdown_v2(f'{nifty_change:+.2%}')}\\)\n\n"
        "_Use /check for real\\-time updates_"
    )
    await context.bot.send_message(chat_id=NOTIFICATION_CHAT_ID, text=message, parse_mode=ParseMode.MARKDOWN_V2)

async def manual_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually check and report current stock prices."""
    try:
        sensex_data = get_stock_data(SENSEX_SYMBOL)
        nifty_data = get_stock_data(NIFTY_SYMBOL)

        sensex_current, sensex_previous, sensex_change = calculate_price_change(
            sensex_data
        )
        nifty_current, nifty_previous, nifty_change = calculate_price_change(nifty_data)

        if sensex_change is None or nifty_change is None:
            await update.message.reply_text(
                "⚠️ *Insufficient Data*\n\n"
                "Sorry, I couldn't fetch the latest market data\\. "
                "This might be due to market closure or a temporary data issue\\.\n\n"
                "Please try again later\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        message = (
            "📊 *Current Stock Prices*\n\n"
            f"*Sensex:* {escape_markdown_v2(f'{sensex_current:.2f}')} \\({escape_markdown_v2(f'{sensex_change:+.2%}')}\\)\n"
            f"*Nifty:* {escape_markdown_v2(f'{nifty_current:.2f}')} \\({escape_markdown_v2(f'{nifty_change:+.2%}')}\\)\n\n"
            "_Percentage change is from the previous close\\._"
        )

        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)

    except Exception as e:
        logger.error(f"Error in manual check: {e}")
        await update.message.reply_text(
            "❌ *Error*\n\n"
            "I encountered an issue while fetching the current prices\\. "
            "Please try again later or contact the bot administrator if the problem persists\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

def ist_to_utc(ist_time_str):
    """Convert IST time string to UTC datetime."""
    ist_time = datetime.strptime(ist_time_str, "%H:%M").time()
    ist_datetime = datetime.combine(datetime.now(IST).date(), ist_time)
    ist_datetime = IST.localize(ist_datetime)
    return ist_datetime.astimezone(UTC)

def utc_to_ist(utc_datetime):
    """Convert UTC datetime to IST datetime."""
    return utc_datetime.astimezone(IST)

async def update_morning_job(application: Application) -> None:
    """Update the job for morning updates based on the new MORNING_UPDATE_TIME."""
    job_queue = application.job_queue
    
    # Remove existing morning update job if any
    for job in job_queue.jobs():
        if job.data and job.data.get('is_morning_update', False):
            job.schedule_removal()
    
    # Schedule new morning update job
    utc_time = ist_to_utc(MORNING_UPDATE_TIME)
    job_queue.run_daily(
        check_prices,
        time=utc_time.time(),
        days=(0, 1, 2, 3, 4, 5, 6),  # Run every day
        data={'is_morning_update': True}
    )

async def set_morning_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the morning update time."""
    global MORNING_UPDATE_TIME
    
    if not context.args or len(context.args) != 1:
        await update.message.reply_text(
            "⚠️ Please provide the time in HH:MM format \\(IST\\)\\. For example: `/set_morning_time 09:15`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    new_time = context.args[0]
    try:
        # Validate the time format
        datetime.strptime(new_time, "%H:%M")
        MORNING_UPDATE_TIME = new_time
        
        # Update the job for morning updates
        await update_morning_job(context.application)
        
        # Convert to UTC for display
        utc_time = ist_to_utc(MORNING_UPDATE_TIME)
        
        await update.message.reply_text(
            f"✅ Morning update time has been set to {escape_markdown_v2(MORNING_UPDATE_TIME)} IST "
            f"\\({escape_markdown_v2(utc_time.strftime('%H:%M'))} UTC\\)\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid time format\\. Please use HH:MM format \\(IST\\)\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )


def main() -> None:
    """Set up and run the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("check", manual_check))
    application.add_handler(CommandHandler("stop_alerts", stop_alerts))
    application.add_handler(CommandHandler("resume_alerts", resume_alerts))
    application.add_handler(CommandHandler("status", get_status))
    application.add_handler(CommandHandler("set_morning_time", set_morning_time))

    # Set up job to check prices periodically
    job_queue = application.job_queue
    job_queue.run_repeating(check_prices, interval=CHECK_INTERVAL, first=10, data={'is_morning_update': False})

    # Set up initial morning update job
    application.job_queue.run_once(update_morning_job, when=0, data={'application': application})

    # Run the bot
    application.run_polling()

if __name__ == "__main__":
    main()