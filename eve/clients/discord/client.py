import argparse
import os
import re
import time
from typing import Optional
import discord
import logging
from discord.ext import commands
from dotenv import load_dotenv

from eve.agent import Agent
from eve.clients import common
from eve.clients.discord import config
from eve.tool import get_tools_from_mongo
from eve.llm import UserMessage, async_prompt_thread, UpdateType
from eve.thread import Thread
from eve.eden_utils import prepare_result

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
        agent: Agent,
        agent_id: Optional[str] = None,
        db: str = "STAGE",
    ) -> None:
        self.bot = bot
        self.agent = agent
        self.agent_id = agent_id
        self.db = db

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message) -> None:
        if message.author.id == self.bot.user.id or message.author.bot:
            return

        is_dm = message.channel.type == discord.ChannelType.private
        if is_dm:
            thread_name = f"discord9-DM-{message.author.name}-{message.author.id}"
            if message.author.id not in common.DISCORD_DM_WHITELIST:
                return
        else:
            thread_name = (
                f"discord9-{message.guild.id}-{message.channel.id}-{message.author.id}"
            )
            trigger_reply = is_mentioned(message, self.bot.user)
            if not trigger_reply:
                return
        logger.info(f"thread_name: {thread_name}")

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

        tools = get_tools_from_mongo(db=self.db)

        thread = Thread.get_collection(self.db).find_one(
            {
                "name": thread_name,
            }
        )
        thread_id = thread.get("_id") if thread else None
        if not thread:
            logger.info("Creating new thread")
            thread = Thread.create(
                db=self.db,
                user=self.agent.owner,
                agent=self.agent_id,
                name=thread_name,
            )
            thread_id = str(thread.id)
        logger.info(f"thread: {thread_id}")

        user_message = UserMessage(content=content)
        ctx = await self.bot.get_context(message)

        async with ctx.channel.typing():
            answered = False
            async for msg in async_prompt_thread(
                db=self.db,
                user_id=self.agent.owner,
                agent_id=self.agent_id,
                thread_id=thread_id,
                user_messages=user_message,
                tools=tools,
            ):
                if msg.type == UpdateType.ASSISTANT_MESSAGE:
                    content = msg.message.content
                    if content:
                        if not answered:
                            await reply(message, content)
                        else:
                            await send(message, content)
                        answered = True
                elif msg.type == UpdateType.TOOL_COMPLETE:
                    msg.result["result"] = prepare_result(
                        msg.result["result"], db="STAGE"
                    )
                    url = msg.result["result"][0]["output"][0]["url"]
                    tool_name = msg.tool_name
                    hour_timestamps[message.author.id].append(
                        {"time": time.time(), "tool": tool_name}
                    )
                    day_timestamps[message.author.id].append(
                        {"time": time.time(), "tool": tool_name}
                    )
                    await send(message, url)
                    logger.info(f"tool called {tool_name}")
                elif msg.type == UpdateType.ERROR:
                    await reply(message, msg.error)

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

    def set_intents(self, intents: discord.Intents) -> None:
        intents.message_content = True
        intents.messages = True
        intents.presences = True
        intents.members = True

    async def on_ready(self) -> None:
        logger.info("Running bot...")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        await self.process_commands(message)


def start(
    env: str,
    agent_path: Optional[str] = None,
    agent_key: Optional[str] = None,
    db: str = "STAGE",
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info("Launching bot...")
    load_dotenv(env)
    agent = common.get_agent(agent_path, agent_key, db=db)
    logger.info(f"Using agent: {agent}")
    bot = DiscordBot()
    bot.add_cog(Eden2Cog(bot, agent, db=db))
    bot.run(os.getenv("CLIENT_DISCORD_TOKEN"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DiscordBot")
    parser.add_argument("--agent_path", help="Path to the agent directory")
    parser.add_argument("--agent_key", help="Key of the agent")
    parser.add_argument("--db", help="Database to use", default="STAGE")
    parser.add_argument("--env", help="Path to the .env file to load", default=".env")
    args = parser.parse_args()
    start(args.env, args.agent_path, args.agent_key, args.db)
