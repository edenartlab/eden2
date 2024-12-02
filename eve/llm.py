

from bson import ObjectId
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ValidationError
from pydantic.config import ConfigDict
from pydantic.json_schema import SkipJsonSchema
from typing import List, Optional, Dict, Any, Literal, Union
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from sentry_sdk import add_breadcrumb, capture_exception, capture_message
import sentry_sdk
import traceback
import os
import json
import asyncio
import openai
import anthropic
import magic
import instructor

from eve.mongo2 import Document, Collection, get_collection
from eve.eden_utils import pprint, download_file, image_to_base64, prepare_result
from eve.task import Task
from eve.tool import Tool, get_tools_from_mongo
from eve.models import User

# from eve.thread import UserMessage, AssistantMessage, ToolCall, Thread
from eve.thread import UserMessage, AssistantMessage, ToolCall, Thread

anthropic_client = anthropic.AsyncAnthropic()
openai_client = openai.AsyncOpenAI()


async def async_anthropic_prompt(
    messages: List[Union[UserMessage, AssistantMessage]], 
    system_message: str = "You are a helpful assistant.", 
    response_model: Optional[BaseModel] = None, 
    tools: Dict[str, Tool] = {},
    db: str = "STAGE"
):
    messages_json = [
        item for msg in messages for item in msg.anthropic_schema()
    ]

    # print("MESSAGES JSON")
    # pprint(messages_json)

    prompt = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 8192,
        "messages": messages_json,
        "system": system_message,
    }

    if response_model:
        anthropic_tools = [t.anthropic_schema(exclude_hidden=True) for t in tools.values()]
        prompt["tools"] = anthropic_tools
        prompt["tool_choice"] = "required"
        
    elif tools:
        anthropic_tools = [t.anthropic_schema(exclude_hidden=True) for t in tools.values()]
        prompt["tools"] = anthropic_tools

    response = await anthropic_client.messages.create(**prompt)

    content = ". ".join([r.text for r in response.content if r.type == "text" and r.text])
    tool_calls = [ToolCall.from_anthropic(r, db=db) for r in response.content if r.type == "tool_use"]
    stop = response.stop_reason != "tool_use"

    return content, tool_calls, stop



async def async_openai_prompt(
    messages: List[Union[UserMessage, AssistantMessage]], 
    system_message: str = "You are a helpful assistant.", 
    response_model: Optional[BaseModel] = None, 
    tools: Dict[str, Tool] = {},
    db: str = "STAGE"
):
    messages_json = [
        item for msg in messages for item in msg.openai_schema()
    ]


    openai_tools = [t.openai_schema(exclude_hidden=True) for t in tools.values()] if tools else None
    response = await openai_client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        tools=openai_tools,
        messages=messages_json,
    )
    response = response.choices[0]

    content = response.message.content or ""
    tool_calls = [ToolCall.from_openai(t, db=db) for t in response.message.tool_calls or []]
    stop = response.finish_reason != "tool_calls"
    
    return content, tool_calls, stop

# def anthropic_prompt(messages, system_message, response_model=None, tools={}):
#     return asyncio.run(async_anthropic_prompt(messages, system_message, response_model, tools))

# def openai_prompt(messages, system_message, tools={}):
#     return asyncio.run(async_openai_prompt(messages, system_message, tools))



from enum import Enum
from typing import Optional, Dict, Any

class UpdateType(str, Enum):
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_COMPLETE = "tool_complete"
    ERROR = "error"

class ThreadUpdate(BaseModel):
    type: UpdateType
    message: Optional[AssistantMessage] = None
    tool_name: Optional[str] = None
    tool_index: Optional[int] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)



async def async_think():
    pass

async def async_prompt_thread(
    db: str,
    user_id: str, 
    agent_id: str,
    thread_id: str,
    user_messages: Union[UserMessage, List[UserMessage]], 
    tools: Dict[str, Tool],
    provider: Literal["anthropic", "openai"] = "anthropic"
):
    user_messages = user_messages if isinstance(user_messages, List) else [user_messages]
    user = User.load(user_id, db=db)
    thread = Thread.load(thread_id, db=db)

    assert thread.user == user.id, "User does not own thread {thread_id}"

    thread.push("messages", user_messages)

    # think = True
    # if think:
    #     thought = await async_think(thread.messages, tools)


    while True:
        try:
            async_prompt_provider = {
                "anthropic": async_anthropic_prompt,
                "openai": async_openai_prompt
            }[provider]

            content, tool_calls, stop = await async_prompt_provider(
                thread.messages, 
                tools=tools
            )
            assistant_message = AssistantMessage(
                content=content or "",
                tool_calls=tool_calls,
                reply_to=user_messages[-1].id
            )
            thread.push("messages", assistant_message)
            assistant_message = thread.messages[-1]
            yield ThreadUpdate(
                type=UpdateType.ASSISTANT_MESSAGE,
                message=assistant_message
            )

        except Exception as e:
            capture_exception(e)
            traceback.print_exc()

            assistant_message = AssistantMessage(
                content="I'm sorry, but something went wrong internally. Please try again later.",
                reply_to=user_messages[-1].id
            )
            thread.push("messages", assistant_message)

            yield ThreadUpdate(
                type=UpdateType.ERROR,
                message=assistant_message
            )
            break
        
        for t, tool_call in enumerate(assistant_message.tool_calls):
            try:
                tool = tools.get(tool_call.tool)
                if not tool:
                    raise Exception(f"Tool {tool_call.tool} not found.")

                task = await tool.async_start_task(user.id, tool_call.args, db=db)
                thread.update_tool_call(assistant_message.id, t, {
                    "task": ObjectId(task.id),
                    "status": "pending"
                })
                
                result = await tool.async_wait(task)
                thread.update_tool_call(assistant_message.id, t, result)

                if result["status"] == "completed":
                    yield ThreadUpdate(
                        type=UpdateType.TOOL_COMPLETE,
                        tool_name=tool_call.tool,
                        tool_index=t,
                        result=result
                    )
                else:
                    yield ThreadUpdate(
                        type=UpdateType.ERROR,
                        tool_name=tool_call.tool,
                        tool_index=t,
                        error=result.get("error")
                    )
                
            except Exception as e:
                capture_exception(e)
                traceback.print_exc()

                thread.update_tool_call(assistant_message.id, t, {
                    "status": "failed",
                    "error": str(e)
                })

                yield ThreadUpdate(
                    type=UpdateType.ERROR,
                    tool_name=tool_call.tool,
                    tool_index=t,
                    error=str(e)
                )

        if stop:
            break


def prompt_thread(
    db: str,
    user_id: str, 
    thread_name: str,
    user_messages: Union[UserMessage, List[UserMessage]], 
    tools: Dict[str, Tool],
    provider: Literal["anthropic", "openai"] = "anthropic"
):
    async_gen = async_prompt_thread(db, user_id, thread_name, user_messages, tools, provider)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        while True:
            try:
                yield loop.run_until_complete(async_gen.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


def print_message(message, name):
    if isinstance(message, AssistantMessage):
        tool_calls = "\n\t".join([f"{t.tool}: {t.get_result()}" for t in message.tool_calls])
        print(f"\n\n===============================\n{name}: {message.content}\n\n{tool_calls}")
    elif isinstance(message, UserMessage):
        print(f"\n\n===============================\n{name}: {message.content}")



def pretty_print_messages(messages, schema: Literal["anthropic", "openai"] = "openai"):
    if schema == "anthropic":
        messages = [item for msg in messages for item in msg.anthropic_schema(truncate_images=True)]
    elif schema == "openai":
        messages = [item for msg in messages for item in msg.openai_schema(truncate_images=True)]
    json_str = json.dumps(messages, indent=4)
    print(json_str)






# @retry(
#     retry=retry_if_exception(lambda e: isinstance(e, (
#         openai.RateLimitError, anthropic.RateLimitError
#     ))),
#     wait=wait_exponential(multiplier=5, max=60),
#     stop=stop_after_attempt(3),
#     reraise=True
# )
# @retry(
#     retry=retry_if_exception(lambda e: isinstance(e, (
#         openai.APIConnectionError, openai.InternalServerError, 
#         anthropic.APIConnectionError, anthropic.InternalServerError
#     ))),
#     wait=wait_exponential(multiplier=2, max=30),
#     stop=stop_after_attempt(3),
#     reraise=True
# )
# async def prompt_llm_and_validate(messages, system_message, provider, tools):
#     num_attempts, max_attempts = 0, 3
#     while num_attempts < max_attempts:
#         num_attempts += 1 
#         # pretty_print_messages(messages, schema=provider)

#         # try:
#         if 1:
#             if provider == "anthropic":
#                 content, tool_calls, stop = await async_anthropic_prompt(messages, system_message, tools)
#             elif provider == "openai":
#                 content, tool_calls, stop = await async_openai_prompt(messages, system_message, tools)
            
#             # check for hallucinated tools
#             invalid_tools = [t.name for t in tool_calls if not t.name in tools]
#             if invalid_tools:
#                 add_breadcrumb(category="invalid_tools", data={"invalid": invalid_tools})
#                 raise ToolNotFoundException(*invalid_tools)

#             # check for hallucinated urls
#             url_pattern = r'https://(?:eden|edenartlab-stage-(?:data|prod))\.s3\.amazonaws\.com/\S+\.(?:jpg|jpeg|png|gif|bmp|webp|mp4|mp3|wav|aiff|flac)'
#             valid_urls  = [url for m in messages if type(m) == UserMessage and m.attachments for url in m.attachments]  # attachments
#             valid_urls += [url for m in messages if type(m) == ToolResultMessage for result in m.tool_results if result and result.result for url in re.findall(url_pattern, result.result)]  # output results 
#             tool_calls_urls = re.findall(url_pattern, ";".join([json.dumps(tool_call.input) for tool_call in tool_calls]))
#             invalid_urls = [url for url in tool_calls_urls if url not in valid_urls]
#             if invalid_urls:
#                 add_breadcrumb(category="invalid_urls", data={"invalid": invalid_urls, "valid": valid_urls})
#                 raise UrlNotFoundException(*invalid_urls)
#             return content, tool_calls, stop

#         # if there are still hallucinations after max_attempts, just let the LLM deal with it
#         # except (ToolNotFoundException, UrlNotFoundException) as e:
#         #     if num_attempts == max_attempts:
#         #         return content, tool_calls, stop





"""

messages = [
    UserMessage(
        name="alice", 
        content="hey bob, what did you think about the zine?"
    ),
    UserMessage(
        name="bob",
        # content="it was pretty good. i really liked the line about the salton sea predictions for 2032."
        content = ""
    ),
    UserMessage(
        name="alice", 
        content="yeah mine too. i was thinking it could be cool to make a reel about it. something with this style.",
        attachments=[
            "https://edenartlab-prod-data.s3.us-east-1.amazonaws.com/bb88e857586a358ce3f02f92911588207fbddeabff62a3d6a479517a646f053c.jpg"
        ]
    ),
]


messages2 = [
    UserMessage(
        content="eve, make a picture of a fancy cat"
    )
]



pretty_print_messages(messages, schema="anthropic")
print("\n\n==========\n\n")
pretty_print_messages(messages, schema="openai")

from eve.thread import Agent2
agent = Agent2.load_from_dir("agents/eve", db="STAGE")

# agent.prompt_thread()
"""