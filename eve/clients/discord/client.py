import argparse
import os
import re
import time
import discord
import json
import logging
from discord.ext import commands
from dotenv import load_dotenv

from eve.sdk.eden import EdenClient
from eve.sdk.eden.client import EdenApiUrls
from eve.clients import common
from eve.clients.discord import config

# Add logger setup
logger = logging.getLogger(__name__)


def is_mentioned(message: discord.Message, user: discord.User) -> bool:
    """
    Checks if a user is mentioned in a message.
    :param message: The message to check.
    :param user: The user to check.
    :return: True if the user is mentioned, False otherwise.
    """
    bot_name = message.guild.me.name
    name_mentioned = (
        re.search(rf"\b{re.escape(bot_name.lower())}\b", message.content.lower())
        is not None
    )
    return name_mentioned or user.id in [m.id for m in message.mentions]


def replace_bot_mention(
    message_text: str,
    only_first: bool = True,
    replacement_str: str = "",
) -> str:
    """
    Removes all mentions from a message.
    :param message: The message to remove mentions from.
    :return: The message with all mentions removed.
    """
    if only_first:
        return re.sub(r"<@\d+>", replacement_str, message_text, 1)
    else:
        return re.sub(r"<@\d+>", replacement_str, message_text)


def replace_mentions_with_usernames(
    message_content: str,
    mentions,
    prefix: str = "",
    suffix: str = "",
) -> str:
    """
    Replaces all mentions with their usernames.
    :param message_content: The message to replace mentions in.
    :return: The message with all mentions replaced with their usernames.
    """
    for mention in mentions:
        message_content = re.sub(
            f"<@!?{mention.id}>",
            f"{prefix}{mention.display_name}{suffix}",
            message_content,
        )
    return message_content.strip()


hour_timestamps = {}
day_timestamps = {}


def user_over_rate_limits(user_id):
    if user_id not in hour_timestamps:
        hour_timestamps[user_id] = []
    if user_id not in day_timestamps:
        day_timestamps[user_id] = []

    hour_timestamps[user_id] = [
        t for t in hour_timestamps[user_id] if time.time() - t["time"] < 3600
    ]
    day_timestamps[user_id] = [
        t for t in day_timestamps[user_id] if time.time() - t["time"] < 86400
    ]

    hour_video_tool_calls = len(
        [t for t in hour_timestamps[user_id] if t["tool"] in common.VIDEO_TOOLS]
    )
    hour_image_tool_calls = len(
        [t for t in hour_timestamps[user_id] if t["tool"] not in common.VIDEO_TOOLS]
    )

    day_video_tool_calls = len(
        [t for t in day_timestamps[user_id] if t["tool"] in common.VIDEO_TOOLS]
    )
    day_image_tool_calls = len(
        [t for t in day_timestamps[user_id] if t["tool"] not in common.VIDEO_TOOLS]
    )

    if (
        hour_video_tool_calls >= common.HOUR_VIDEO_LIMIT
        or hour_image_tool_calls >= common.HOUR_IMAGE_LIMIT
    ):
        return True
    if (
        day_video_tool_calls >= common.DAY_VIDEO_LIMIT
        or day_image_tool_calls >= common.DAY_IMAGE_LIMIT
    ):
        return True
    return False


class Eden2Cog(commands.Cog):
    def __init__(
        self,
        bot: commands.bot,
    ) -> None:
        self.bot = bot

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message) -> None:
        current_time = time.time()
        if current_time - self.bot.last_refresh_time > 300:
            self.bot.last_refresh_time = current_time

        logger.info(f"on... message ... {message.content}\n=============")

        if message.author.id == self.bot.user.id or message.author.bot:
            return

        is_dm = message.channel.type == discord.ChannelType.private
        if is_dm:
            thread_name = f"discord9-DM-{message.author.name}-{message.author.id}"
            if message.author.id not in common.DISCORD_DM_WHITELIST:
                return
        else:
            thread_name = f"discord9-{message.guild.name}-{message.channel.id}-{message.author.id}"
            trigger_reply = is_mentioned(message, self.bot.user)
            if not trigger_reply:
                return

        if user_over_rate_limits(message.author.id):
            await reply(
                message,
                "I'm sorry, you've hit your rate limit. Please try again a bit later!",
            )
            return

        content = replace_bot_mention(message.content, only_first=True)
        content = replace_mentions_with_usernames(content, message.mentions)

        if message.reference:
            source_message = await message.channel.fetch_message(
                message.reference.message_id
            )
            content = f"(Replying to message: {source_message.content[:100]} ...)\n\n{content}"

        chat_message = {
            "name": message.author.name,
            "content": content,
            "attachments": [attachment.url for attachment in message.attachments],
            "settings": {},
        }
        logger.info(f"chat message {chat_message}")

        ctx = await self.bot.get_context(message)
        async with ctx.channel.typing():
            answered = False
            async for update in self.bot.eden_client.async_chat(chat_message, thread_name):
                if update["type"] == "ASSISTANT_MESSAGE":
                    content = update["content"]
                    if content:
                        if not answered:
                            await reply(message, content)
                        else:
                            await send(message, content)
                        answered = True
                elif update["type"] == "TOOL_COMPLETE":
                    tool_name = update["tool"]
                    hour_timestamps[message.author.id].append(
                        {"time": time.time(), "tool": tool_name}
                    )
                    day_timestamps[message.author.id].append(
                        {"time": time.time(), "tool": tool_name}
                    )
                    logger.info(f"tool called {tool_name}")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        logger.info(f"{member} has joined the guild id: {member.guild.id}")
        await member.send(config.WELCOME_MESSAGE.format(name=member.name))


async def reply(message, content):
    content_chunks = [content[i : i + 1980] for i in range(0, len(content), 1980)]
    for c, chunk in enumerate(content_chunks):
        await message.reply(chunk) if c == 0 else await message.channel.send(chunk)


async def send(message, content):
    content_chunks = [content[i : i + 1980] for i in range(0, len(content), 1980)]
    for c, chunk in enumerate(content_chunks):
        await message.channel.send(chunk)


class DiscordBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        self.set_intents(intents)
        commands.Bot.__init__(
            self,
            command_prefix="!",
            intents=intents,
        )
        api_urls: EdenApiUrls = EdenApiUrls(
            api_url=os.getenv("EDEN_API_URL") or "http://localhost:5050",
            tools_api_url=os.getenv("EDEN_TOOLS_API_URL") or "http://127.0.0.1:8000",
        )
        self.eden_client = EdenClient(api_urls=api_urls)
        self.last_refresh_time = time.time()

    def set_intents(self, intents: discord.Intents) -> None:
        intents.message_content = True
        intents.messages = True
        intents.presences = True
        intents.members = True

    def get_commands(self) -> None:
        bot_data = self.db["commands"].find_one({"bot": "eden"})
        if bot_data:
            return bot_data.get("commands", [])
        else:
            return []

    def allowed_guilds(self, command_name) -> None:
        command = self.bot_commands.get(command_name)
        if command:
            return command.get("guilds", None)
        else:
            return None

    async def on_ready(self) -> None:
        logger.info("Running bot...")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        await self.process_commands(message)


def start(
    env: str,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info("Launching bot...")
    load_dotenv(env)
    bot = DiscordBot()
    bot.add_cog(Eden2Cog(bot))
    bot.run(os.getenv("DISCORD_TOKEN"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DiscordBot")
    parser.add_argument("--env", help="Path to the .env file to load", default=".env")
    args = parser.parse_args()
    start(args.env)
