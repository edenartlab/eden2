import sys
sys.path.append("../..")

from agent import Agent
from mongo import get_collection
from bson import ObjectId
from thread import UserMessage, async_prompt, Thread


async def chat(args: dict, user: str = None, env: str = "STAGE"):
    agent = Agent.from_id(args["agent_id"], env=env)

    if args["thread_id"]:
        threads = get_collection("threads", env=env)
        thread = threads.find_one({"_id": ObjectId(args["thread_id"])})
        if not thread:
            raise Exception("Thread not found")
        thread = Thread.from_id(args["thread_id"], env=env)
    else:
        thread = Thread(env=env)

    message = UserMessage(
        content=args["content"],
        attachments=args["attachments"]
    )

    results = [
        response.model_dump_json() 
        async for response in async_prompt(thread, agent, message)
    ]
        
    return {"messages": results}
