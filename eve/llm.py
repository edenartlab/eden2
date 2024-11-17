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

from eve.mongo2 import Document
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
    created_at: datetime = Field(default_factory=datetime.utcnow)

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
    status: Optional[Literal["pending", "running", "completed", "failed", "cancelled"]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
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
    #     task = await self.tool.async_start_task(user_id, self.input, db="STAGE")
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






# thread = Thread.load("6736a16b6da49686528217bd", db="STAGE")
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
# anthropic consider names in group chat
# verify hidden from agent works right, and tips
# validate args before tool wait
# sentry thread
# tidy up handle_wait

# X ? pushing granular updates instead of .save()

# X multiple user messages / multiple assistant messages
# order by createdAt
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
# tools = get_tools_from_mongo(tools=["txt2img", "animate_3D"], db="STAGE")
# tools = get_tools_from_mongo(tools=["news", "example_tool", "flux_schnell", "animate_3D", "runway"], db="STAGE")
# tools = get_tools_from_mongo(tools=["example_tool"],db="STAGE")
tools = get_tools_from_mongo(db="STAGE")



# messages = [
#     UserMessage(content="Hello, how are you?"),
#     AssistantMessage(content="I'm good, thanks for asking.")
# ]
# pprint(messages)

user_id = os.getenv("EDEN_TEST_USER_STAGE")


from eve.mongo2 import Document, Collection

@Collection("threads2")
class Thread(Document):
    name: str
    user: ObjectId
    messages: List[Union[UserMessage, AssistantMessage]] = []

    def update_tool_call(self, message_id, tool_call_index, updates):

        # this should validate too?

        for key, value in updates.items():
            message = next(m for m in self.messages if m.id == message_id)
            setattr(message.tool_calls[tool_call_index], key, value)
        
        self.update2({
            f"messages.$.tool_call.{k}": v for k, v in updates.items()
        }, filter={"messages.id": message_id})



    # @classmethod
    # def get_collection_name(cls) -> str:
    #     return "threads2"

    # def add_messages(self, *new_messages, save=False):
    #     self.messages.extend(new_messages)
    #     if save:
    #         payload = {"$each": [m.model_dump() for m in new_messages]}
    #         self.push({"messages": payload})

    # def update_message(self, message_id, updates):
    #     updates = {f"messages.$.{k}": v for k, v in updates.items()}
    #     self.update2(updates, filter={"messages.id": message_id})


        # thread.update_message(assistant_message.id, {
        #     f"tool_calls.{t}.task": ObjectId(task.id),
        #     f"tool_calls.{t}.status": "pending"
        # })

        
        # f"messages.5.tool_calls.{t}.task": ObjectId(task.id),
        # f"messages.5.tool_calls.{t}.result": {"status": "pending"}


# thread = Thread.load("6737ab65f27a1cc88397a361", db="STAGE")




# print(thread.messages)

# thread = Thread(db="STAGE", name="test575", user=ObjectId(user_id))
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
    print("this is the current state of the assistant message AT THE BEG")
    pprint(thread)


    print("THREAD")
    pprint(thread)
    print("----")


    print("---765456 THIS IS THE FINAL ANTHROPIC CALL")
    pprint(thread.messages)

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

    # thread.add_messages(assistant_message, save=True)
    thread.push("messages", assistant_message)
    # Get reference to the pushed message
    assistant_message = thread.messages[-1]
    
    for t, tool_call in enumerate(assistant_message.tool_calls):
        # try:
        if 1:
            tool = tools[tool_call.tool]
            task = await tool.async_start_task(
                user_id, tool_call.args, db="STAGE"
            )
            print("the task312  is", task)


            thread.update_tool_call(assistant_message.id, t, {
                "task": ObjectId(task.id),
                "status": "pending"
            })

            result = await tool.async_wait(task)

            thread.update_tool_call(assistant_message.id, t, result)


            print("---- 8888 the assistant message")
            pprint(assistant_message.tool_calls)

        # except Exception as e:
        #     tool_call.result = {"error": str(e)}

        # thread.save()

    print("this is the current state of the assistant message AT THE END")
    pprint(thread)

    return stop



async def test2():
    print("ok 1")
    thread = Thread(db="STAGE", name="test102", user=ObjectId(user_id))
    print("ok 2")
    messages = [
        UserMessage(content="hi there!!."),
        UserMessage(content="do you hear me?"),
        UserMessage(content="Hello, tell me something now."),
        AssistantMessage(content="I have a cat."),
        AssistantMessage(content="Apples are bananers."),
        UserMessage(content="what did you just say? repeat everything you said verbatim."),
        UserMessage(content="hello?"),
        AssistantMessage(content="I said Apples are bananers."),
        UserMessage(content="no"),
        UserMessage(content="you said something before that"),
    ]

    messages = [
        UserMessage(name="jim", content="i have an apple."),
        UserMessage(name="kate", content="the capital of france is paris?"),
        UserMessage(name="morgan", content="what is even going on here?"),
        UserMessage(name="scott", content="i am you?"),
        UserMessage(content="what did morgan say?"),
    ]
    print("ok 3")
    # thread.push("messages", messages[0])
    # thread.push("messages", messages[1])
    # thread.push("messages", messages[2])
    print("ok 4")
    thread.save()
    print("ok 5")
    thread.messages = messages

    content, tool_calls, stop = await async_openai_prompt(
        thread.messages, 
        "You are a helpful assistant.", 
        tools=tools
    )

    print("CONTENT", content)



if __name__ == "__main__":
    asyncio.run(test2())

