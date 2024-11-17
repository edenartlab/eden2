"""
user_message = UserMessage(
    role='user',
    user=ObjectId, (discord_user, twitter_user, etc)  ( -> this is name)
    attachments=Dict()
)
User (Clerk, Web3Auth):
    userId

Agent(MongoModel)
    auth_user:
    is_user: true|false
    has manna
    has profile
    has rate limits
    description: 
    instructions: 



    


Concepts(MongoVersionableModel)
    base_model:
    edits:
    original
    current


ChatMessage(MongoModel)
    role: Literal["user", "assistant", "system", "tool"]
    agent: AgentVersion

class UserMessage(ChatMessage):
    role: Literal["user"] = "user"
    (name is derived from super.agent) 
    content: str
    concepts: Optional[Dict[str, ConceptVersion]] = None
    attachments: Optional[List[str]] = None


class ToolCall(BaseModel):
    id: str
    name: str
    input: Dict[str, Any]


class ToolResult(BaseModel):
    id: str
    name: str
    result: Optional[Any] = None
    error: Optional[str] = None

class AssistantMessage(ChatMessage):
    role: Literal["assistant"] = "assistant"
    (name is derived from super.agent) 
    content: Optional[str] = ""
    thought: Optional[str] = ""
    tool_calls: Optional[List[ToolCall]] = Field(None, description="Tool calls")
    finish_reason?

Thread:
    auth_user:
    slug: 
    messages: List[ChatMessage]

think:
    receives a new user message
    observes, makes plan, makes intentions
    intentions:
        intentions: 
        chat: true|false

"""



from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Dict, Any, Literal, Union
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from sentry_sdk import add_breadcrumb, capture_exception, capture_message
from pydantic.config import ConfigDict
import os
import re
import json
import asyncio
import random
import sentry_sdk

import openai
import anthropic

from eve.mongo import MongoModel
from eve.eden_utils import pprint, download_file, image_to_base64
from eve.task import Task
import json
from eve.tool import Tool
import anthropic
from pydantic.json_schema import SkipJsonSchema

anthropic_client = anthropic.AsyncAnthropic()
openai_client = openai.AsyncOpenAI()


class ChatMessage(BaseModel):
    id: ObjectId = Field(default_factory=ObjectId, alias="_id")
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )


class UserMessage(ChatMessage):
    name: Optional[str] = None
    content: str
    metadata: Optional[Dict[str, Any]] = {}
    attachments: Optional[List[str]] = []

    def _get_content(self, schema, truncate_images=False):
        content_str = self.content
        if self.metadata:
            content_str += f"\n\n## Metadata: \n\n{json.dumps(self.metadata)}"
        if self.attachments:
            attachment_urls = ',\n\t'.join([f'"{url}"' for url in self.attachments])  # Convert HttpUrl to string
            content_str += f"\n\n## Attachments:\n\n[\n\t{attachment_urls}\n]"        
        content = content_str or ""
        
        if self.attachments:
            attachment_files = [
                download_file(attachment, os.path.join("/tmp/eden_file_cache/", attachment.split("/")[-1]), overwrite=False) 
                for attachment in self.attachments
            ]

            if schema == "anthropic":
                content = [{
                    "type": "image", 
                    "source": {
                        "type": "base64", 
                        "media_type": "image/jpeg",
                        "data": image_to_base64(file_path, max_size=512, quality=95, truncate=truncate_images)
                    }
                } for file_path in attachment_files]
            elif schema == "openai":
                content = [{
                    "type": "image_url", 
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_to_base64(file_path, max_size=512, quality=95, truncate=truncate_images)}"
                    }
                } for file_path in attachment_files]

            content.extend([{"type": "text", "text": content_str}])
                        
        return content
    
    def anthropic_schema(self, truncate_images=False):
        return [{
            "role": "user",
            "content": self._get_content("anthropic", truncate_images=truncate_images)
        }]

    def openai_schema(self, truncate_images=False):
        return [{
            "role": "user",
            "content": self._get_content("openai", truncate_images=truncate_images),
            **({"name": self.name} if self.name else {})
        }]





class ToolCall(BaseModel):
    id: str
    tool: str
    args: Dict[str, Any]
    
    task: Optional[ObjectId] = None
    result: Optional[Dict[str, Any]] = {"status": "pending"}
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )

    @staticmethod
    def from_openai(tool_call):
        return ToolCall(
            id=tool_call.id,
            tool=tool_call.function.name,
            args=json.loads(tool_call.function.arguments),
        )
    
    @staticmethod
    def from_anthropic(tool_call):
        print("TOOL CALL")
        print(tool_call)
        return ToolCall(
            id=tool_call.id,
            tool=tool_call.name,
            args=tool_call.input,
        )
    
    # async def run(self):
    #     task = await self.tool.async_start_task(user_id, self.input, env="STAGE")
    #     self.result = await self.tool.async_wait(task)

    def validate(self, tools):
        pass #tbd
    
    def openai_call_schema(self):
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.tool,
                "arguments": json.dumps(self.args)
            }
        }
    
    def anthropic_call_schema(self):
        return {
            "type": "tool_use",
            "id": self.id,
            "name": self.tool,
            "input": self.args
        }
    
    def anthropic_result_schema(self):
        return {
            "type": "tool_result",
            "tool_use_id": self.id,
            "content": json.dumps(self.result)
        }
    
    def openai_result_schema(self):
        return {
            "role": "tool",
            "name": self.tool,
            "content": json.dumps(self.result),
            "tool_call_id": self.id
        }
            
    

class AssistantMessage(ChatMessage):
    reply_to: Optional[int] = None
    thought: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = []
    
    def openai_schema(self, truncate_images=False):
        schema = [{
            "role": "assistant",
            "content": self.content,
            "function_call": None,
            "tool_calls": None
        }]
        if self.tool_calls:
            schema[0]["tool_calls"] = [t.openai_call_schema() for t in self.tool_calls]
            schema.extend([t.openai_result_schema() for t in self.tool_calls])        
        return schema
    
    def anthropic_schema(self, truncate_images=False):
        schema = [{
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": self.content
                }
            ],
        }]
        if self.tool_calls:
            schema[0]["content"].extend([
                t.anthropic_call_schema() for t in self.tool_calls
            ])
            schema.append({
                "role": "user",
                "content": [t.anthropic_result_schema() for t in self.tool_calls]
            })
        return schema

    # async def run_tool_calls(self, tool_calls):
    #     for tool_call in self.tool_calls:
    #         result = await tool_call.run()
    #         print("THE RESULT IS", result)
    #         print("this is the ned")






# thread = Thread.load("6736a16b6da49686528217bd", env="STAGE")
# messages_json = [item for msg in thread.messages for item in msg.anthropic_schema()]




from pydantic import BaseModel
import anthropic
import instructor

def anthropic_prompt2(messages, system_message, response_model):
    client = instructor.from_anthropic(anthropic.Anthropic())
    result = client.messages.create(
        model="claude-3.5-sonnet-20240620",
        max_tokens=1024,
        max_retries=0,
        messages=messages,
        # system_message=system_message,
        response_model=response_model
    )
    return result





async def async_anthropic_prompt(messages, system_message, response_model=None, tools={}):
    print("lets run anthropic")
    messages_json = [item for msg in messages for item in msg.anthropic_schema()]
    
    print(json.dumps(messages_json, indent=2))
    
    prompt = {
        "model": "claude-3-5-sonnet-20240620",
        "max_tokens": 8192,
        "messages": messages_json,
        "system": system_message,
    }

    if response_model:
        # prompt["response_model"] = response_model
        anthropic_tools = [t.anthropic_schema(exclude_hidden=True) for t in tools.values()]
        prompt["tools"] = anthropic_tools
        prompt["tool_choice"] = "required"
        pass
    elif tools:
        anthropic_tools = [t.anthropic_schema(exclude_hidden=True) for t in tools.values()]
        prompt["tools"] = anthropic_tools

    response = await anthropic_client.messages.create(**prompt)
    print("2222")
    print(response)
    print("3333")
    # text_messages = [r.text for r in response.content if r.type == "text" and r.text]
    content = ". ".join([r.text for r in response.content if r.type == "text" and r.text])
    print("THE CONTENT IS... ", content)
    tool_calls = [ToolCall.from_anthropic(r) for r in response.content if r.type == "tool_use"]
    print("TOOL CALLS", tool_calls)
    print("STOP REASON", response.stop_reason)
    stop = response.stop_reason != "tool_use"
    return content, tool_calls, stop


def anthropic_prompt(messages, system_message, response_model=None, tools={}):
    return asyncio.run(async_anthropic_prompt(messages, system_message, response_model, tools))




async def async_openai_prompt(messages, system_message, tools={}):
    messages_json = [item for msg in messages for item in msg.openai_schema()]

    print(json.dumps(messages_json, indent=2))
    openai_tools = [t.openai_schema(exclude_hidden=True) for t in tools.values()]
    print("-----")
    # print(json.dumps(openai_tools["example_tool"], indent=2))
    response = await openai_client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        tools=openai_tools,
        messages=messages_json,
    )
    response = response.choices[0]        
    content = response.message.content or ""
    tool_calls = [ToolCall.from_openai(t) for t in response.message.tool_calls or []]
    stop = response.finish_reason != "tool_calls"
    return content, tool_calls, stop


def openai_prompt(messages, system_message, tools={}):
    return asyncio.run(async_openai_prompt(messages, system_message, tools))


# X ? what to do about empty text ("this is a test")
# multiple user messages / multiple assistant messages
# order by createdAt
# verify hidden from agent works right, and tips
# validate args before tool wait
# sentry thread
# tidy up handle_wait

# pushing granular updates instead of .save()


# make sure to use reply_to to peg assistant
# contain last 10-15 messages
# if reply to by old message, include context leading up to it
# use reply_to index

# vision (make sure it knows thumbnail is a video, or try mp4 vision tool
# add attachments to s3 and get bytes
# use filename not url, abstract url, url handling (substitute for fake links)
# reactions (string)

# thread creating and loading by name/slugs
# hook up agents

# cli (eve chat)
# long instructions open ended test
# think - decide to reply
# test group chat





from eve.tool import get_tools_from_mongo
# tools = get_tools_from_mongo(tools=["txt2img", "animate_3D"],env="STAGE")
# tools = get_tools_from_mongo(tools=["news", "example_tool", "flux_schnell", "animate_3D", "runway"],env="STAGE")
# tools = get_tools_from_mongo(tools=["example_tool"],env="STAGE")
tools = get_tools_from_mongo(env="STAGE")



# messages = [
#     UserMessage(content="Hello, how are you?"),
#     AssistantMessage(content="I'm good, thanks for asking.")
# ]
# pprint(messages)

user_id = os.getenv("EDEN_TEST_USER_STAGE")





class Thread(MongoModel):
    name: str
    user: ObjectId
    messages: List[Union[UserMessage, AssistantMessage]] = []


    @classmethod
    def get_collection_name(cls) -> str:
        return "threads2"

    def add_messages(self, *new_messages, save=False):
        self.messages.extend(new_messages)
        if save:
            payload = {"$each": [m.model_dump() for m in new_messages]}
            self.push({"messages": payload})

    def update_message(self, message_id, updates):
        updates = {f"messages.$.{k}": v for k, v in updates.items()}
        self.set(updates, filter={"messages.id": message_id})
        # f"messages.5.tool_calls.{t}.task": ObjectId(task.id),
        # f"messages.5.tool_calls.{t}.result": {"status": "pending"}


thread = Thread.load("6737ab65f27a1cc88397a361", env="STAGE")


# thread = Thread(env="STAGE", name="test101", user=ObjectId(user_id))
# # thread.add_messages(*messages)
# thread.save()


# print(thread.messages)

# thread = Thread(env="STAGE", name="test575", user=ObjectId(user_id))
# # thread.add_messages(*messages)
# thread.save()

# thread.add_messages(UserMessage(content="can you make a picture of a fancy dog? go for it"), save=True)


# async def go():
#     print("Go1")
#     content, tool_calls, stop = await async_anthropic_prompt(
#         thread.messages, 
#         "You are a helpful assistant.", 
#         tools=tools
#     )
#     print("Go2")
#     print("TOOL CALLS", tool_calls)
#     assistant_message = AssistantMessage(
#         # reply_to=user_message_id,
#         content=content or "this is a test",
#         tool_calls=tool_calls
#     )
#     print("Go3")
#     print(assistant_message)
#     return assistant_message

# import asyncio
# assistant_message=asyncio.run(go())

# thread.add_messages(assistant_message, save=True)
# print("RES", assistant_message)


# t = 0
# thread.update_message(assistant_message.id, {
#     f"tool_calls.{t}.task": ObjectId("6737a0331a7d221613247ec7"),
#     f"tool_calls.{t}.result": {"status": "pending!!!"}
# })


# thread.set2(
#     {
#         f"tool_calls.{t}.task": ObjectId("6737a0331a7d221613247ec7"),
#         f"tool_calls.{t}.result": {"status": "DONE!!"}
#     }, {
#         "messages.message_id": assistant_message.id
#     }
# )


# raise Exception("TEST")
async def run_thread(thread: Thread):
    print("RUN THREAD")

    # raise Exception("TEST")

    # try:
    if 1:
        # content, tool_calls, stop = await async_anthropic_prompt(
        # content, tool_calls, stop = await async_openai_prompt(

        content, tool_calls, stop = await async_anthropic_prompt(
            thread.messages, 
            "You are a helpful assistant.", 
            tools=tools
        )
        assistant_message = AssistantMessage(
            # reply_to=user_message_id,
            content=content or "",
            tool_calls=tool_calls
        )
    
    # except Exception as e:
    #     print("THERE IS A PROBLEM!!!")
    #     assistant_message = AssistantMessage(
    #         # reply_to=user_message_id,
    #         content=f"I'm sorry, something went wrong: {e}"
    #     )
    #     tool_calls = []
    #     stop = True

    thread.add_messages(assistant_message, save=True)
    # thread.save()

    for t, tool_call in enumerate(tool_calls):
        # try:
        if 1:
            tool = tools[tool_call.tool]
            task = await tool.async_start_task(
                user_id, tool_call.args, env="STAGE"
            )
            print("the task312  is", task)

            # tool_call.task = task.id
            # tool_call.result = {"status": "pending"}

            # settle this structure


            thread.update_message(assistant_message.id, {
                f"tool_calls.{t}.task": ObjectId(task.id),
                f"tool_calls.{t}.status": "pending"
            })



            result = await tool.async_wait(task)
            print("the result is 223123", result)
            # tool_call.result.update(result)


            updates = {f"tool_calls.{t}.{k}": v for k, v in result.items()}
            print("--- 777 udpates", updates)
            thread.update_message(assistant_message.id, updates)


        # except Exception as e:
        #     tool_call.result = {"error": str(e)}

        # thread.save()

    return stop

