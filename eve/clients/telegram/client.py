import os
import argparse
import json
import re
import time
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from eden.client import EdenClient, EdenApiUrls

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
LONG_RUNNING_TOOLS = {"txt2vid", "style_mixing", "img2vid", "vid2vid", "video_upscale",
                      "vid2vid_sdxl", "lora_trainer", "animate_3D", "reel", "story"}
VIDEO_TOOLS = {"animate_3D", "txt2vid", "img2vid", "vid2vid_sdxl", "style_mixing",
               "video_upscaler", "reel", "story", "lora_trainer"}

# Rate limits
HOUR_IMAGE_LIMIT = 50
HOUR_VIDEO_LIMIT = 10
DAY_IMAGE_LIMIT = 200
DAY_VIDEO_LIMIT = 40

hour_timestamps = {}
day_timestamps = {}

async def handler_mention_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Determine if the bot is mentioned or replied to.
    """
    message = update.message
    chat_type = message.chat.type
    is_direct_message = chat_type == 'private'
    bot_username = (await context.bot.get_me()).username.lower()

    is_bot_mentioned = any(
        entity.type == 'mention' and 
        message.text[entity.offset:entity.offset + entity.length].lower() == f"@{bot_username}"
        for entity in message.entities or []
    )

    is_replied_to_bot = bool(message.reply_to_message and message.reply_to_message.from_user.username.lower() == bot_username)
    return message.chat.id, chat_type, is_direct_message, is_bot_mentioned, is_replied_to_bot

def get_user_info(update: Update):
    """
    Retrieve user information from the update.
    """
    user = update.message.from_user
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return user.id, user.username, user.first_name or "", user.last_name or "", full_name

def remove_bot_mentions(message_text: str, bot_username: str) -> str:
    """
    Remove bot mentions from the message text.
    """
    pattern = rf"\s*@{re.escape(bot_username)}\b"
    return re.sub(pattern, "", message_text, flags=re.IGNORECASE).strip().replace('  ', ' ')

def user_over_rate_limits(user_id):
    """
    Check if the user has exceeded the rate limits.
    """
    current_time = time.time()
    
    # Filter timestamps within valid intervals
    hour_timestamps[user_id] = [t for t in hour_timestamps.get(user_id, []) if current_time - t["time"] < 3600]
    day_timestamps[user_id] = [t for t in day_timestamps.get(user_id, []) if current_time - t["time"] < 86400]
    
    hour_video_count = sum(1 for t in hour_timestamps[user_id] if t["tool"] in VIDEO_TOOLS)
    hour_image_count = len(hour_timestamps[user_id]) - hour_video_count
    
    day_video_count = sum(1 for t in day_timestamps[user_id] if t["tool"] in VIDEO_TOOLS)
    day_image_count = len(day_timestamps[user_id]) - day_video_count
    
    return (hour_video_count >= HOUR_VIDEO_LIMIT or hour_image_count >= HOUR_IMAGE_LIMIT or
            day_video_count >= DAY_VIDEO_LIMIT or day_image_count >= DAY_IMAGE_LIMIT)

async def send_response(message_type: str, chat_id: int, response: list, context: ContextTypes.DEFAULT_TYPE):
    """
    Send messages or photos based on the type of response.
    """
    for item in response:
        if item.startswith("https://"):
            logging.info(f"Sending photo to {chat_id}")
            await context.bot.send_photo(chat_id=chat_id, photo=item)
        else:
            logging.info(f"Sending message to {chat_id}")
            await context.bot.send_message(chat_id=chat_id, text=item)

class EdenTG:
    def __init__(self, token: str):
        self.token = token
        self.eden_client = EdenClient(stage=False)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handler for the /start command.
        """
        await update.message.reply_text("Hello! I am your asynchronous bot.")

    async def echo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle incoming messages and process bot mentions or direct messages.
        """
        chat_id, _, is_direct_message, is_bot_mentioned, is_replied_to_bot = await handler_mention_type(update, context)
        user_id, user_name, _, _, _ = get_user_info(update)
        
        # Determine message type
        message_type = (
            "dm" if is_direct_message else 
            "mention" if is_bot_mentioned else 
            "reply" if is_replied_to_bot else 
            None
        )
        if not message_type:
            return
        
        # Process text or photo messages
        message_text = update.message.text or ""
        if update.message.photo:
            photo_url = (await update.message.photo[-1].get_file()).file_path
            logging.info(f"Received photo from {user_name}: {photo_url}")
        else:
            cleaned_text = remove_bot_mentions(message_text, (await context.bot.get_me()).username)
            logging.info(f"Received message from {user_name}: {cleaned_text}")
        
        # Mock response
        response = [
            "Hello, I am the Eden Telegram Bot.",
            "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1732713849/creations/h8oh82rzapnnile2yjms.jpg"
        ]
        await send_response(message_type, chat_id, response, context)

def main(env_path: str):
    load_dotenv(env_path)
    bot_token = os.getenv("TELEGRAM_TOKEN")
    
    application = ApplicationBuilder().token(bot_token).build()
    eden_bot = EdenTG(bot_token)
    
    application.add_handler(CommandHandler("start", eden_bot.start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, eden_bot.echo))
    application.add_handler(MessageHandler(filters.PHOTO, eden_bot.echo))
    
    application.add_error_handler(lambda update, context: logging.error("Exception:", exc_info=context.error))
    
    logging.info("Bot started.")
    application.run_polling()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Eden Telegram Bot")
    parser.add_argument("--env", help="Path to the .env file to load", default=".env")
    args = parser.parse_args()
    main(args.env)
