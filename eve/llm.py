# messages -> messages with urls prepared
# messages with urls prepared -> substituted urls

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
import instructor

from eve.mongo2 import Document, Collection, get_collection
from eve.eden_utils import pprint, download_file, image_to_base64, prepare_result
from eve.task import Task
from eve.tool import Tool, get_tools_from_mongo
from eve.models import User

anthropic_client = anthropic.AsyncAnthropic()
openai_client = openai.AsyncOpenAI()


class ChatMessage(BaseModel):
    id: ObjectId = Field(default_factory=ObjectId)#, alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    
    db: SkipJsonSchema[str]
    task: Optional[ObjectId] = None
    status: Optional[Literal["pending", "running", "completed", "failed", "cancelled"]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )

    def _get_result(self):
        result = {"status": self.status}
        if self.status == "completed":
            result["result"] = prepare_result(self.result, db=self.db)
        elif self.status == "failed":
            result["error"] = self.error
        return json.dumps(result)

    @staticmethod
    def from_openai(tool_call, db="STAGE"):
        return ToolCall(
            id=tool_call.id,
            tool=tool_call.function.name,
            args=json.loads(tool_call.function.arguments),
            db=db
        )
    
    @staticmethod
    def from_anthropic(tool_call, db="STAGE"):
        return ToolCall(
            id=tool_call.id,
            tool=tool_call.name,
            args=tool_call.input,
            db=db
        )
    
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
            "content": self._get_result()
        }
    
    def openai_result_schema(self):
        return {
            "role": "tool",
            "name": self.tool,
            "content": self._get_result(),
            "tool_call_id": self.id
        }
            
class AssistantMessage(ChatMessage):
    reply_to: Optional[ObjectId] = None
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


@Collection("threads2")
class Thread(Document):
    name: str
    user: ObjectId
    messages: List[Union[UserMessage, AssistantMessage]] = []

    @classmethod
    def from_name(cls, name, user, db="STAGE"):
        threads = get_collection("threads2", db=db)
        thread = threads.find_one({"name": name, "user": user})
        if not thread:
            new_thread = cls(db=db, name=name, user=user)
            new_thread.save()
            return new_thread
        else:
            return cls(**thread, db=db)

    def update_tool_call(self, message_id, tool_call_index, updates):
        # Update the in-memory object
        for key, value in updates.items():
            message = next(m for m in self.messages if m.id == message_id)
            setattr(message.tool_calls[tool_call_index], key, value)
        # Update the database
        self.set_against_filter({
            f"messages.$.tool_calls.{tool_call_index}.{k}": v for k, v in updates.items()
        }, filter={"messages.id": message_id})


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


async def async_openai_prompt(messages, system_message, tools={}, db="STAGE"):
    messages_json = [item for msg in messages for item in msg.openai_schema()]

    openai_tools = [t.openai_schema(exclude_hidden=True) for t in tools.values()]
    # print(json.dumps(openai_tools["example_tool"], indent=2))
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

def anthropic_prompt(messages, system_message, response_model=None, tools={}):
    return asyncio.run(async_anthropic_prompt(messages, system_message, response_model, tools))

def openai_prompt(messages, system_message, tools={}):
    return asyncio.run(async_openai_prompt(messages, system_message, tools))


async def async_prompt_thread(
    db: str,
    user_id: str, 
    thread_name: str,
    user_message: UserMessage, 
    tools: Dict[str, Tool]
):
    user = User.load(user_id, db=db)
    thread = Thread.from_name(name=thread_name, user=user.id, db=db)
    thread.push("messages", user_message)

    while True:
        try:
            content, tool_calls, stop = await async_anthropic_prompt(
                thread.messages, 
                tools=tools
            )
            assistant_message = AssistantMessage(
                content=content or "",
                tool_calls=tool_calls,
                reply_to=user_message.id
            )
            thread.push("messages", assistant_message)
            assistant_message = thread.messages[-1]
            yield assistant_message

        except Exception as e:
            assistant_message = AssistantMessage(
                content="I'm sorry, but something went wrong internally. Please try again later.",
                reply_to=user_message.id
            )
            thread.push("messages", assistant_message)
            capture_exception(e)
            traceback.print_exc()
            yield assistant_message
            # break
            return
        
        for t, tool_call in enumerate(assistant_message.tool_calls):
            tool = tools.get(tool_call.tool)
            if not tool:
                thread.update_tool_call(assistant_message.id, t, {
                    "task": ObjectId(task.id),
                    "status": "failed",
                    "error": f"Tool {tool_call.tool} not found."
                })
                continue
            
            try:
                task = await tool.async_start_task(user.id, tool_call.args, db=db)
                thread.update_tool_call(assistant_message.id, t, {
                    "task": ObjectId(task.id),
                    "status": "pending"
                })
                result = await tool.async_wait(task)
                thread.update_tool_call(assistant_message.id, t, result)
                yield result
            
            except Exception as e:
                thread.update_tool_call(assistant_message.id, t, {
                    "status": "failed",
                    "error": str(e)
                })
                capture_exception(e)
                traceback.print_exc()

        if stop:
            #break
            return


# i think this might not be right
def prompt_thread(db, user_id, thread_name, user_message, tools):
    async def run():
        return [msg async for msg in async_prompt_thread(db, user_id, thread_name, user_message, tools)]
    
    return asyncio.run(run())

