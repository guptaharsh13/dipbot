import os
import asyncio
import logging
from datetime import datetime, timedelta
import yfinance as yf
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

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
        "threshold": float(os.getenv("ALERT_THRESHOLD_1", "0.01")),
        "emoji": "⚠️",
        "prefix": "ALERT",
    },
    {
        "threshold": float(os.getenv("ALERT_THRESHOLD_2", "0.03")),
        "emoji": "🚨",
        "prefix": "WARNING",
    },
    {
        "threshold": float(os.getenv("ALERT_THRESHOLD_3", "0.06")),
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        "Welcome to the Refined Indian Stock Market Monitor Bot!"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "Available commands:\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/check - Manually check current stock prices\n"
        "/stop_alerts - Pause alerts until next morning\n"
        "/resume_alerts - Resume alerts\n"
        "/status - Get current bot status"
    )
    await update.message.reply_text(help_text)


async def stop_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pause alerts until next morning."""
    global alerts_paused
    alerts_paused = True
    await update.message.reply_text(
        "Alerts have been paused until the next morning update."
    )


async def resume_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume alerts."""
    global alerts_paused
    alerts_paused = False
    await update.message.reply_text("Alerts have been resumed.")


async def get_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Get current bot status."""
    status_message = (
        f"Bot Status:\n"
        f"Alerts: {'Paused' if alerts_paused else 'Active'}\n"
        f"Alert Thresholds: {', '.join([f'{t:.1%}' for t in ALERT_THRESHOLDS])}\n"
        f"Check Interval: {CHECK_INTERVAL} seconds\n"
        f"Morning Update Time: {MORNING_UPDATE_TIME}"
    )
    await update.message.reply_text(status_message)


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
        current_time = datetime.now().time()
        morning_update_time = datetime.strptime(MORNING_UPDATE_TIME, "%H:%M").time()

        # Reset alerts_paused flag at the morning update time
        if (
            current_time.hour == morning_update_time.hour
            and current_time.minute == morning_update_time.minute
        ):
            alerts_paused = False

        sensex_data = get_stock_data(SENSEX_SYMBOL)
        nifty_data = get_stock_data(NIFTY_SYMBOL)

        sensex_current, sensex_previous, sensex_change = calculate_price_change(
            sensex_data
        )
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

        # Send morning update
        if (
            current_time.hour == morning_update_time.hour
            and current_time.minute == morning_update_time.minute
        ):
            await send_daily_status(
                context, sensex_current, nifty_current, sensex_change, nifty_change
            )

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
        if price_change <= -level["threshold"]:
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
    """Send an alert message for a specific index with formatting based on the alert level."""
    message = (
        f"{alert_level['emoji']} {alert_level['prefix']}: {index_name} "
        f"down {abs(price_change):.2%}\n\n"
        f"Current: {current_price:.2f}\n"
        f"Previous: {previous_close:.2f}\n"
        f"Change: {price_change:.2%}\n\n"
        f"Threshold: {alert_level['threshold']:.1%}\n"
        f"Use /stop_alerts to pause"
    )
    logger.info(f"Sending {alert_level['prefix']} alert for {index_name}")
    await context.bot.send_message(chat_id=NOTIFICATION_CHAT_ID, text=message)


async def send_daily_status(
    context: ContextTypes.DEFAULT_TYPE,
    sensex_price: float,
    nifty_price: float,
    sensex_change: float,
    nifty_change: float,
) -> None:
    """Send daily morning status update."""
    message = f"📊 Daily Market Update ({MORNING_UPDATE_TIME}):\n\n"
    message += f"Sensex: {sensex_price:.2f} ({sensex_change:+.2%})\n"
    message += f"Nifty: {nifty_price:.2f} ({nifty_change:+.2%})"
    await context.bot.send_message(chat_id=NOTIFICATION_CHAT_ID, text=message)


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
                "Sorry, insufficient data is available. The market might be closed or there might be a data issue."
            )
            return

        message = f"Current Stock Prices:\n"
        message += (
            f"Sensex: {sensex_current:.2f} ({sensex_change:+.2%} from previous close)\n"
        )
        message += (
            f"Nifty: {nifty_current:.2f} ({nifty_change:+.2%} from previous close)"
        )

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Error in manual check: {e}")
        await update.message.reply_text(
            "Sorry, there was an error fetching the current prices. Please try again later."
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

    # Set up job to check prices periodically
    job_queue = application.job_queue
    job_queue.run_repeating(check_prices, interval=CHECK_INTERVAL, first=10)

    # Run the bot
    application.run_polling()


if __name__ == "__main__":
    main()
