from bson import ObjectId
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ValidationError
from pydantic.config import ConfigDict
from pydantic.json_schema import SkipJsonSchema
from typing import List, Optional, Dict, Any, Literal, Union
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from sentry_sdk import add_breadcrumb, capture_exception, capture_message
import re
import sentry_sdk
import traceback
import os
import json
import asyncio
import openai
import anthropic
import magic
import instructor
from instructor.function_calls import openai_schema

from eve.mongo import Document, Collection, get_collection
from eve.eden_utils import pprint, download_file, image_to_base64, prepare_result
from eve.task import Task
from eve.tool import Tool, get_tools_from_mongo
from eve.user import User
from eve.agent import Agent

# from eve.thread import UserMessage, AssistantMessage, ToolCall, Thread
from eve.thread import UserMessage, AssistantMessage, ToolCall, Thread

from jinja2 import Template



async def async_anthropic_prompt(
    messages: List[Union[UserMessage, AssistantMessage]], 
    system_message: Optional[str] = "You are a helpful assistant.", 
    model: str = "claude-3-5-sonnet-20241022",
    response_model: Optional[type[BaseModel]] = None, 
    tools: Dict[str, Tool] = None,
    db: str = "STAGE"
):
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise ValueError("ANTHROPIC_API_KEY env is not set")
        
    messages_json = [
        item for msg in messages for item in msg.anthropic_schema()
    ]
    prompt = {
        "model": model,
        "max_tokens": 8192,
        "messages": messages_json,
        "system": system_message,
    }

    anthropic_client = anthropic.AsyncAnthropic()
    
    if tools or response_model:
        tools = [t.anthropic_schema(exclude_hidden=True) for t in (tools or {}).values()]
        if response_model:
            tools.append(openai_schema(response_model).anthropic_schema)
            prompt["tool_choice"] = {"type": "tool", "name": response_model.__name__}
        prompt["tools"] = tools

    response = await anthropic_client.messages.create(**prompt)

    if response_model:
        return response_model(**response.content[0].input)

    else:
        content = ". ".join([r.text for r in response.content if r.type == "text" and r.text])
        tool_calls = [ToolCall.from_anthropic(r, db=db) for r in response.content if r.type == "tool_use"]
        stop = response.stop_reason != "tool_use"
        return content, tool_calls, stop


async def async_openai_prompt(
    messages: List[Union[UserMessage, AssistantMessage]], 
    system_message: Optional[str] = "You are a helpful assistant.", 
    model: str = "gpt-4o-mini", # "gpt-4o-2024-08-06",
    response_model: Optional[type[BaseModel]] = None, 
    tools: Dict[str, Tool] = {},
    db: str = "STAGE"
):
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY env is not set")

    messages_json = [
        item for msg in messages for item in msg.openai_schema()
    ]
    if system_message:
        messages_json = [{"role": "system", "content": system_message}] + messages_json

    openai_client = openai.AsyncOpenAI()
    
    if response_model:
        response = await openai_client.beta.chat.completions.parse(
            model=model,
            messages=messages_json,
            response_format=response_model
        )
        return response.choices[0].message.parsed

    else:
        tools = [t.openai_schema(exclude_hidden=True) for t in tools.values()] if tools else None
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages_json,
            tools=tools
        )
        response = response.choices[0]
        content = response.message.content or ""
        tool_calls = [ToolCall.from_openai(t, db=db) for t in response.message.tool_calls or []]
        stop = response.finish_reason != "tool_calls"
        
        return content, tool_calls, stop


@retry(
    retry=retry_if_exception(lambda e: isinstance(e, (
        openai.RateLimitError, anthropic.RateLimitError
    ))),
    wait=wait_exponential(multiplier=5, max=60),
    stop=stop_after_attempt(3),
    reraise=True
)
@retry(
    retry=retry_if_exception(lambda e: isinstance(e, (
        openai.APIConnectionError, openai.InternalServerError, 
        anthropic.APIConnectionError, anthropic.InternalServerError
    ))),
    wait=wait_exponential(multiplier=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True
)
async def async_prompt(
    messages: List[Union[UserMessage, AssistantMessage]], 
    system_message: Optional[str] = "You are a helpful assistant.", 
    model: str = "claude-3-5-sonnet-20241022",
    response_model: Optional[type[BaseModel]] = None, 
    tools: Dict[str, Tool] = {},
    db: str = "STAGE"
):    
    if model.startswith("claude"):
        return await async_anthropic_prompt(
            messages, system_message, model, response_model, tools, db
        )
    else:
        return await async_openai_prompt(
            messages, system_message, model, response_model, tools, db
        )

def anthropic_prompt(messages, system_message, model, response_model=None, tools=None):
    return asyncio.run(async_anthropic_prompt(messages, system_message, model, response_model, tools))

def openai_prompt(messages, system_message, model, response_model=None, tools=None):
    return asyncio.run(async_openai_prompt(messages, system_message, model, response_model, tools))

def prompt(messages, system_message, model, response_model=None, tools=None):
    return asyncio.run(async_prompt(messages, system_message, model, response_model, tools))



from enum import Enum
from typing import Optional, Dict, Any

class UpdateType(str, Enum):
    START_PROMPT = "start_prompt"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_COMPLETE = "tool_complete"
    ERROR = "error"

models = [
    "claude-3-5-sonnet-20241022",
    "gpt-4o-mini",
    "gpt-4o-2024-08-06"
]


# todo: `msg.error` not `msg.message.error`
class ThreadUpdate(BaseModel):
    type: UpdateType
    message: Optional[AssistantMessage] = None
    tool_name: Optional[str] = None
    tool_index: Optional[int] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


system_instructions = """In addition to the instructions above, follow these additional guidelines:
* In your response, do not include anything besides for your chat message. Do not include pretext, stage directions, or anything other than what you are saying.
* Do not apologize.
* Try to be concise. Do not be verbose.
"""

template = '''<Summary>You are roleplaying as {{ name }}.</Summary>
<Description>
This is a description of {{ name }}.

{{ description }}
</Description>
<Instructions>
{{ instructions }}
</Instructions>
<System Instructions>
{{ system_instructions }}
</System Instructions>'''

async def async_think():
    # - think (gpt3)
    # - choose tools
    # - choose knowledge
    # - which tools to make available
    # - decide to reply
    # - make intentions
    pass

async def async_prompt_thread(
    db: str,
    user_id: str, 
    agent_id: str,
    thread_id: Optional[str],
    user_messages: Union[UserMessage, List[UserMessage]], 
    tools: Dict[str, Tool],
    force_reply: bool = True,
    model: Literal[tuple(models)] = "claude-3-5-sonnet-20241022"
):
    agent = Agent.from_mongo(agent_id, db=db)
    user = User.from_mongo(user_id, db=db)
    thread = Thread.from_mongo(thread_id, db=db)

    if thread.allowlist:
        assert user.id in thread.allowlist, "User is not allowed to post in thread {thread_id}"

    user_messages = user_messages if isinstance(user_messages, List) else [user_messages]

    system_message = Template(template).render(
        name=agent.name,
        description=agent.description,
        instructions=agent.instructions,
        system_instructions=system_instructions
    )

    print("HERE IS THE SYSTEM MESSAGE!!!")
    print(system_message)
    thread.push("messages", user_messages)

    agent_mentioned = any(
        re.search(rf'\b{re.escape(agent.name.lower())}\b', (msg.content or "").lower())
        for msg in user_messages
    )

    if not agent_mentioned and not force_reply:
        return

    # think = True
    # if think:
    #     thought = await async_think(thread.messages, tools)

    yield ThreadUpdate(type=UpdateType.START_PROMPT)

    while True:
        try:
            print("lets go to", model)
            content, tool_calls, stop = await async_prompt(
                thread.get_messages(), 
                system_message=system_message,
                model=model,
                tools=tools
            )
            print("HERE IS THE CONTENT!!!")
            print(content)
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
                message=assistant_message,
                error=str(e)
            )
            break
        
        for t, tool_call in enumerate(assistant_message.tool_calls):
            try:
                tool = tools.get(tool_call.tool)
                if not tool:
                    raise Exception(f"Tool {tool_call.tool} not found.")

                task = await tool.async_start_task(user.id, agent.id, tool_call.args, db=db)
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
    agent_id: str,
    thread_id: Optional[str],
    user_messages: Union[UserMessage, List[UserMessage]], 
    tools: Dict[str, Tool],
    force_reply: bool = False,
    model: Literal[tuple(models)] = "gpt-4o-mini" # "claude-3-5-sonnet-20241022"
):
    async_gen = async_prompt_thread(db, user_id, agent_id, thread_id, user_messages, tools, force_reply, model)
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
