"""
Weather Alert Bot
Fetches weather from OpenWeatherMap and alerts on conditions.
"""
import os
import asyncio
import logging
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "3600"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))
CITY = os.getenv("CITY", "Tehran")
ALERT_RAIN = os.getenv("ALERT_RAIN", "true").lower() in ("1", "true", "yes")
ALERT_WIND = int(os.getenv("ALERT_WIND", "20"))

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

subscribers: set = set()
last_alert: dict = {}


def is_admin(chat_id: Any) -> bool:
    if not ADMIN_CHAT_ID:
        return True
    return str(chat_id) in ADMIN_CHAT_ID.split(",")


async def fetch_weather() -> Optional[dict]:
    if not OPENWEATHER_API_KEY:
        return None
    url = "https://api.openweathermap.org/data/2.5/weather"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(url, params={"q": CITY, "appid": OPENWEATHER_API_KEY, "units": "metric"})
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        logger.warning(f"Weather fetch failed: {e}")
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    await update.message.reply_text(
        "🌦 Weather Alert Bot\n\n"
        "/subscribe - Subscribe to alerts\n"
        "/unsubscribe - Unsubscribe\n"
        "/weather - Current weather\n"
        "/status - Status"
    )


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    if not is_admin(update.effective_chat.id):
        return
    subscribers.add(update.effective_chat.id)
    await update.message.reply_text("✅ Subscribed to weather alerts.")


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    subscribers.discard(update.effective_chat.id)
    await update.message.reply_text("✅ Unsubscribed.")


async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    data = await fetch_weather()
    if not data:
        await update.message.reply_text("❌ Failed to fetch weather.")
        return
    main = data["main"]
    wind = data.get("wind", {})
    weather = data["weather"][0]
    text = (
        f"🌦 Weather in {CITY}\n\n"
        f"{weather['description'].capitalize()}\n"
        f"🌡 Temp: {main['temp']}°C\n"
        f"💧 Humidity: {main['humidity']}%\n"
        f"🌬 Wind: {wind.get('speed', 0)} m/s"
    )
    await update.message.reply_text(text)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    await update.message.reply_text(f"📊 Subscribers: {len(subscribers)}\nCity: {CITY}")


async def monitor(app: Application) -> None:
    while True:
        try:
            data = await fetch_weather()
            if not data:
                await asyncio.sleep(CHECK_INTERVAL)
                continue
            weather = data["weather"][0]
            wind = data.get("wind", {})
            wid = weather.get("id", 0)
            wspd = wind.get("speed", 0)
            text = None
            if ALERT_RAIN and 200 <= wid < 700 and "rain" not in last_alert:
                text = f"🌧 <b>Rain Alert in {CITY}!</b>\n\n{weather['description'].capitalize()}\nTemp: {data['main']['temp']}°C"
                last_alert["rain"] = True
            if wspd >= ALERT_WIND and "wind" not in last_alert:
                text = f"🌬 <b>Wind Alert in {CITY}!</b>\n\nWind speed: {wspd} m/s"
                last_alert["wind"] = True
            if text:
                for chat_id in list(subscribers):
                    try:
                        await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
                    except Exception as e:
                        logger.warning(f"Alert failed: {e}")
                    await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


async def post_init(application: Application) -> None:
    asyncio.create_task(monitor(application))
    commands = [BotCommand("start", "Start"), BotCommand("subscribe", "Subscribe"), BotCommand("unsubscribe", "Unsubscribe"), BotCommand("weather", "Weather"), BotCommand("status", "Status")]
    await application.bot.set_my_commands(commands)


def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN missing!")
        return
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", cmd_subscribe))
    application.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    application.add_handler(CommandHandler("weather", cmd_weather))
    application.add_handler(CommandHandler("status", cmd_status))
    application.run_polling()


if __name__ == "__main__":
    main()
