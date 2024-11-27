import os
import asyncio
from eve.llm import *
from eve.tool import get_tools_from_mongo


db = "STAGE"
user_id = os.getenv("EDEN_TEST_USER_STAGE")
thread_name = "test_soc3"

tools = get_tools_from_mongo(db=db)

user_message = UserMessage(
    # content="can you make a picture of a fancy dog?"
    # content="who are you?"
    content="now can you animate that with runway?"
)

async def run_prompt():
    messages = []
    async for message in async_prompt_thread(db, user_id, thread_name, user_message, tools):
        messages.append(message)
    return messages

# result = asyncio.run(run_prompt())
# print(result)

user = User.load(user_id, db=db)
thread = Thread.from_name(name=thread_name, user=user.id, db=db)


thread1 = Thread.from_name(name=thread_name+"_inverse", user=user.id, db=db)
thread1.save()

messages = [
    UserMessage(content="You are my inner voice, guiding me as I create images for you. You must critique my work and give me feedback on how to improve as I give more images to you, and move me forward in my work.")
]
for message in thread.messages:
    if isinstance(message, UserMessage):
        assistant_message = AssistantMessage(
            content=message.content
        )
        messages.append(assistant_message)
    elif isinstance(message, AssistantMessage):
        attachments = []
        for tool_call in message.tool_calls or []:
            result = tool_call.get_result()
            if result.get("status") == "completed":
                attachments.extend(
                    output["url"]
                    for result_item in result.get("result", [])
                    for output in result_item.get("output", [])
                    if "url" in output
                )
        user_message = UserMessage(
            content=message.content,
            attachments=attachments
        )
        messages.append(user_message)


thread1.push("messages", messages)


