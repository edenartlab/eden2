import sys
sys.path.append(".")

from bson import ObjectId
from agent import get_default_agent
from tools import get_tools
from thread import Thread, UserMessage

tools = get_tools("../workflows", exclude=["xhibit/remix", "xhibit/vton", "blend"])

user = ObjectId("65284b18f8bbb9bff13ebe65")  # user = gene3
agent = get_default_agent() # eve

thread = Thread(
    name="test", 
    user=user,
    tools=tools
)

async def test_thread():
    user_message = UserMessage(
        content="how is your day today?", 
    )
    async for message in thread.prompt(agent, user_message):
        print(message)

    user_message = UserMessage(
        content="repeat what you just said",
    )
    async for message in thread.prompt(agent, user_message):
        print(message)


import asyncio
asyncio.run(test_thread())