from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Dict, Any, Literal, Union
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from sentry_sdk import add_breadcrumb, capture_exception, capture_message
import os
import re
import json
import asyncio
import random
import openai
import anthropic
import sentry_sdk
from eve.mongo import MongoModel
from eve.eden_utils import pprint, download_file, image_to_base64
from eve.task import Task
import json

import anthropic
anthropic_client = anthropic.AsyncAnthropic()



class ChatMessage(BaseModel):
    id: int = Field(default_factory=lambda: random.randint(0, 1000))
    createdAt: datetime = Field(default_factory=datetime.utcnow, exclude=True)


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
        content = content_str
        
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


class AssistantMessage(ChatMessage):
    thought: Optional[str] = None
    content: Optional[str] = None
    tasks: Optional[List[Task]] = None
    
    def openai_schema(self, truncate_images=False):
        schema = [{
            "role": "assistant",
            "content": self.content,
            "function_call": None,
            "tool_calls": None
        }]
        if self.tool_calls:
            schema[0]["tool_calls"] = [t.openai_schema() for t in self.tool_calls]
        return schema
    
    def anthropic_schema(self, truncate_images=False):
        schema = [{
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": self.content,
                }
            ],
        }]
        # if self.tool_calls:
        #     schema[0]["content"].extend([
        #         t.anthropic_schema() for t in self.tool_calls
        #     ])
        return schema


from eve.tool import Tool

class ToolCall(BaseModel):
    id: str
    # name: str
    # input: Dict[str, Any]
    # result: Optional[Any] = None
    # error: Optional[str] = None
    
    # tool: Tool
    task: Task = None

    @staticmethod
    def from_openai(tool_call):
        return ToolCall(
            id=tool_call.id,
            name=tool_call.function.name,
            input=json.loads(tool_call.function.arguments),
        )
    
    @staticmethod
    async def from_anthropic(tool, tool_call):
        id = tool_call.id
        task = await tool.async_start_task(user_id, tool_call.input, env="STAGE")
        return ToolCall(id=id, task=task)
    
    def validate(self, tools):
        pass #tbd
    
    def openai_schema(self):
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.input)
            }
        }
    
    def anthropic_schema(self):
        return {
            "type": "tool_use",
            "id": self.id,
            "name": self.name,
            "input": self.input
        }



user_id = os.getenv("EDEN_TEST_USER_STAGE")




async def async_anthropic_prompt(messages, system_message, tools={}):
    messages_json = [item for msg in messages for item in msg.anthropic_schema()]
    anthropic_tools = [t.anthropic_schema(exclude_hidden=True) for t in tools.values()]

    
    
    response = await anthropic_client.messages.create(
        model="claude-3-5-haiku-20241022", #"claude-3-5-sonnet-20240620",
        max_tokens=8192,
        tools=anthropic_tools,
        messages=messages_json,
        system=system_message,
    )


    text_messages = [r.text for r in response.content if r.type == "text"]
    content = text_messages[0] or ""
    tool_calls = [await ToolCall.from_anthropic(tools[r.name], r) for r in response.content if r.type == "tool_use"]

    print("THE TOOL CALLS ARE", tool_calls)

    stop = response.stop_reason == "tool_use"
    return content, tool_calls, stop


def anthropic_prompt(messages, system_message, tools={}):
    return asyncio.run(async_anthropic_prompt(messages, system_message, tools))






from eve.tool import get_tools_from_mongo
tools = get_tools_from_mongo(tools=["txt2img", "animate_3D"],env="STAGE")

messages = [
    UserMessage(content="Hello, how are you?"),
    AssistantMessage(content="I'm good, thanks for asking."),
    UserMessage(content="Can you make a picture of a fancy cat ?")
]
pprint(messages)


result = anthropic_prompt(messages, "You are a helpful assistant.", tools=tools)

print("THE RESULT IS", result)