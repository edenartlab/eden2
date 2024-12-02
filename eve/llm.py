

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


# class ChatMessage(BaseModel):
#     id: ObjectId = Field(default_factory=ObjectId)
#     created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
#     role: Literal["user", "assistant"]

#     model_config = ConfigDict(
#         arbitrary_types_allowed=True
#     )


# class UserMessage(ChatMessage):
#     role: Literal["user"] = "user"
#     name: Optional[str] = None
#     content: str
#     metadata: Optional[Dict[str, Any]] = {}
#     attachments: Optional[List[str]] = []

#     def _get_content(self, schema, truncate_images=False):
#         content_str = self.content
#         if self.metadata:
#             content_str += f"\n\n## Metadata: \n\n{json.dumps(self.metadata)}"
#         if self.attachments:
#             attachment_urls = ',\n\t'.join([f'"{url}"' for url in self.attachments])  # Convert HttpUrl to string
#             content_str += f"\n\n## Attachments:\n\n[\n\t{attachment_urls}\n]"        
#         content = content_str or ""
        
#         if self.attachments:
#             attachment_files = []
#             for attachment in self.attachments:
#                 try:
#                     attachment_file = download_file(attachment, os.path.join("/tmp/eden_file_cache/", attachment.split("/")[-1]), overwrite=False) 
#                     attachment_files.append(attachment_file)
#                     mime_type = magic.from_file(attachment_file, mime=True)
#                     if "video" in mime_type:
#                         content_str += f"\n\n**The attachment {attachment} is a video. Showing just the first frame.**"
#                 except Exception as e:
#                     content_str += f"\n**Error downloading attachment {attachment}: {e}**"

#             if schema == "anthropic":
#                 content = [{
#                     "type": "image", 
#                     "source": {
#                         "type": "base64", 
#                         "media_type": "image/jpeg",
#                         "data": image_to_base64(file_path, max_size=512, quality=95, truncate=truncate_images)
#                     }
#                 } for file_path in attachment_files]
#             elif schema == "openai":
#                 content = [{
#                     "type": "image_url", 
#                     "image_url": {
#                         "url": f"data:image/jpeg;base64,{image_to_base64(file_path, max_size=512, quality=95, truncate=truncate_images)}"
#                     }
#                 } for file_path in attachment_files]

#             content.extend([{"type": "text", "text": content_str}])
                        
#         return content
    
#     def anthropic_schema(self, truncate_images=False):
#         return [{
#             "role": "user",
#             "content": self._get_content("anthropic", truncate_images=truncate_images)
#         }]

#     def openai_schema(self, truncate_images=False):
#         return [{
#             "role": "user",
#             "content": self._get_content("openai", truncate_images=truncate_images),
#             **({"name": self.name} if self.name else {})
#         }]


# class ToolCall(BaseModel):
#     id: str
#     tool: str
#     args: Dict[str, Any]
    
#     db: SkipJsonSchema[str]
#     task: Optional[ObjectId] = None
#     status: Optional[Literal["pending", "running", "completed", "failed", "cancelled"]] = None
#     result: Optional[List[Dict[str, Any]]] = None
#     error: Optional[str] = None
    
#     model_config = ConfigDict(
#         arbitrary_types_allowed=True
#     )

#     def get_result(self):
#         result = {"status": self.status}
#         if self.status == "completed":
#             result["result"] = prepare_result(self.result, db=self.db)
#         elif self.status == "failed":
#             result["error"] = self.error
#         return result

#     @staticmethod
#     def from_openai(tool_call, db="STAGE"):
#         return ToolCall(
#             id=tool_call.id,
#             tool=tool_call.function.name,
#             args=json.loads(tool_call.function.arguments),
#             db=db
#         )
    
#     @staticmethod
#     def from_anthropic(tool_call, db="STAGE"):
#         return ToolCall(
#             id=tool_call.id,
#             tool=tool_call.name,
#             args=tool_call.input,
#             db=db
#         )
    
#     def openai_call_schema(self):
#         return {
#             "id": self.id,
#             "type": "function",
#             "function": {
#                 "name": self.tool,
#                 "arguments": json.dumps(self.args)
#             }
#         }
    
#     def anthropic_call_schema(self):
#         return {
#             "type": "tool_use",
#             "id": self.id,
#             "name": self.tool,
#             "input": self.args
#         }
        
#     def anthropic_result_schema(self):        
#         return {
#             "type": "tool_result",
#             "tool_use_id": self.id,
#             "content": json.dumps(self.get_result())
#         }
    
#     def openai_result_schema(self):
#         return {
#             "role": "tool",
#             "name": self.tool,
#             "content": json.dumps(self.get_result()),
#             "tool_call_id": self.id
#         }


# class AssistantMessage(ChatMessage):
#     role: Literal["assistant"] = "assistant"
#     reply_to: Optional[ObjectId] = None
#     thought: Optional[str] = None
#     content: Optional[str] = None
#     tool_calls: Optional[List[ToolCall]] = []
    
#     def openai_schema(self, truncate_images=False):
#         schema = [{
#             "role": "assistant",
#             "content": self.content,
#             "function_call": None,
#             "tool_calls": None
#         }]
#         if self.tool_calls:
#             schema[0]["tool_calls"] = [t.openai_call_schema() for t in self.tool_calls]
#             schema.extend([t.openai_result_schema() for t in self.tool_calls])        
#         return schema
    
#     def anthropic_schema(self, truncate_images=False):
#         schema = [{
#             "role": "assistant",
#             "content": [
#                 {
#                     "type": "text",
#                     "text": self.content
#                 }
#             ],
#         }]
#         if self.tool_calls:
#             schema[0]["content"].extend([
#                 t.anthropic_call_schema() for t in self.tool_calls
#             ])
#             schema.append({
#                 "role": "user",
#                 "content": [t.anthropic_result_schema() for t in self.tool_calls]
#             })
#         return schema


# @Collection("threads2")
# class Thread(Document):
#     name: str
#     user: ObjectId
#     messages: List[Union[UserMessage, AssistantMessage]] = Field(default_factory=list)

#     @classmethod
#     def from_name(cls, name, user, db="STAGE"):
#         threads = get_collection("threads2", db=db)
#         thread = threads.find_one({"name": name, "user": user})
#         if not thread:
#             new_thread = cls(db=db, name=name, user=user)
#             new_thread.save()
#             return new_thread
#         else:
#             return cls(**thread, db=db)

#     def update_tool_call(self, message_id, tool_call_index, updates):
#         # Update the in-memory object
#         message = next(m for m in self.messages if m.id == message_id)
#         for key, value in updates.items():
#             setattr(message.tool_calls[tool_call_index], key, value)
#         # Update the database
#         self.set_against_filter({
#             f"messages.$.tool_calls.{tool_call_index}.{k}": v for k, v in updates.items()
#         }, filter={"messages.id": message_id})


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

    print("THIS IS THE THREAD!")
    print(thread)

    print(thread.user)
    print(user_id)
    assert thread.user == user.id, "User does not own thread {thread_id}"

    thread.push("messages", user_messages)


    # think = True
    # if think:
    #     thought = await async_think(thread.messages, tools)


    while True:
        # try:
        if 1:
            async_prompt_provider = {
                "anthropic": async_anthropic_prompt,
                "openai": async_openai_prompt
            }[provider]

            content, tool_calls, stop = await async_prompt_provider(
                thread.messages, 
                tools=tools
            )
            print("CONTENT")
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

        # except Exception as e:
        e="A"
        if 0:
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
            # try:
            if 1:
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
                
            # except Exception as e:
            e="A"
            if 0:
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
async def prompt_llm_and_validate(messages, system_message, provider, tools):
    num_attempts, max_attempts = 0, 3
    while num_attempts < max_attempts:
        num_attempts += 1 
        # pretty_print_messages(messages, schema=provider)

        # try:
        if 1:
            if provider == "anthropic":
                content, tool_calls, stop = await async_anthropic_prompt(messages, system_message, tools)
            elif provider == "openai":
                content, tool_calls, stop = await async_openai_prompt(messages, system_message, tools)
            
            # check for hallucinated tools
            invalid_tools = [t.name for t in tool_calls if not t.name in tools]
            if invalid_tools:
                add_breadcrumb(category="invalid_tools", data={"invalid": invalid_tools})
                raise ToolNotFoundException(*invalid_tools)

            # check for hallucinated urls
            url_pattern = r'https://(?:eden|edenartlab-stage-(?:data|prod))\.s3\.amazonaws\.com/\S+\.(?:jpg|jpeg|png|gif|bmp|webp|mp4|mp3|wav|aiff|flac)'
            valid_urls  = [url for m in messages if type(m) == UserMessage and m.attachments for url in m.attachments]  # attachments
            valid_urls += [url for m in messages if type(m) == ToolResultMessage for result in m.tool_results if result and result.result for url in re.findall(url_pattern, result.result)]  # output results 
            tool_calls_urls = re.findall(url_pattern, ";".join([json.dumps(tool_call.input) for tool_call in tool_calls]))
            invalid_urls = [url for url in tool_calls_urls if url not in valid_urls]
            if invalid_urls:
                add_breadcrumb(category="invalid_urls", data={"invalid": invalid_urls, "valid": valid_urls})
                raise UrlNotFoundException(*invalid_urls)
            return content, tool_calls, stop

        # if there are still hallucinations after max_attempts, just let the LLM deal with it
        # except (ToolNotFoundException, UrlNotFoundException) as e:
        #     if num_attempts == max_attempts:
        #         return content, tool_calls, stop





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