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
from eve.user import User
from eve.eden_utils import prepare_result


users = {}



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
            f"<@[!&]?{mention.id}>",
            f"{prefix}{mention.display_name}{suffix}",
            message_content,
        )
    return message_content.strip()


class Eden2Cog(commands.Cog):
    def __init__(
        self,
        bot: commands.bot,
        agent: Agent,
        db: str = "STAGE",
    ) -> None:
        self.bot = bot
        self.agent = agent
        self.db = db
        self.tools = get_tools_from_mongo(db=self.db)

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message) -> None:
        if message.author.id == self.bot.user.id: # or message.author.bot:
            return
        
        dm = message.channel.type == discord.ChannelType.private
        if dm:
            thread_key = f"discord-dm-{message.author.name}-{message.author.id}"
            if message.author.id not in common.DISCORD_DM_WHITELIST:
                return
        else:
            thread_key = (
                f"discord-{message.guild.id}-{message.channel.id}-{message.author.id}"
            )
        logger.info(f"key: {thread_key}")

        # Lookup user
        if message.author.id not in users:
            users[message.author.id] = User.from_discord(
                message.author.id, 
                message.author.name, 
                db=self.db
            )
        user = users[message.author.id]

        # Check user rate limits
        if common.user_over_rate_limits(user):
            await reply(
                message,
                "I'm sorry, you've hit your rate limit. Please try again a bit later!",
            )
            return

        # Replace mentions with usernames
        content = replace_mentions_with_usernames(message.content, message.mentions)


        # Prepend reply to message if it is a reply
        force_reply = False
        if message.reference:
            source_message = await message.channel.fetch_message(
                message.reference.message_id
            )
            force_reply = source_message.author.id == self.bot.user.id
            content = f"(Replying to message: {source_message.content[:100]} ...)\n\n{content}"

        # Get thread
        thread = Thread.get_collection(self.db).find_one({"key": thread_key})
        thread_id = thread.get("_id") if thread else None
        if not thread:
            logger.info("Creating new thread")
            thread = Thread.create(key=thread_key, db=self.db)
            thread_id = thread.id
        logger.info(f"thread: {thread_id}")

        # Create chat message
        user_message = UserMessage(
            content=content,
            name=message.author.name,
            attachments=[attachment.url for attachment in message.attachments],
        )
        logger.info(f"chat message {user_message}")

        ctx = await self.bot.get_context(message)

        replied = False
        typing = None

        async for msg in async_prompt_thread(
            db=self.db,
            user_id=user.id,
            agent_id=self.agent.id,
            thread_id=thread_id,
            user_messages=user_message,
            force_reply=force_reply,
            tools=self.tools,
        ):
            if msg.type == UpdateType.START_PROMPT:
                print("I RECEIVED A START PROMPT")
                await ctx.channel.trigger_typing()
        
            elif msg.type == UpdateType.ERROR:
                await reply(message, msg.error)

            elif msg.type == UpdateType.ASSISTANT_MESSAGE:
                content = msg.message.content
                if content:
                    if not replied:
                        await reply(message, content)
                    else:
                        await send(message, content)
                    replied = True
            
            elif msg.type == UpdateType.TOOL_COMPLETE:
                msg.result["result"] = prepare_result(
                    msg.result["result"], db=self.db
                )
                url = msg.result["result"][0]["output"][0]["url"]
                common.register_tool_call(user, msg.tool_name)
                await send(message, url)
                logger.info(f"tool called {msg.tool_name}")
            


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
        print("process 1")
        await self.process_commands(message)
        print("process 2")

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

    # if agent_path:
    #     agent = Agent.from_yaml(str(agent_path), db=db)
    # elif agent_key:
    #     agent = Agent.load(agent_key, db=db)
    # else:
    #     raise ValueError("Either agent_path or agent_key must be provided")

    agent = Agent.load("verdelis", db=db)

    logger.info(f"Using agent: {agent.name}")
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
