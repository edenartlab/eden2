from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel, Field, ValidationError
from pydantic.config import ConfigDict
from pydantic.json_schema import SkipJsonSchema
from typing import List, Optional, Dict, Any, Literal, Union
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from sentry_sdk import add_breadcrumb, capture_exception, capture_message
import sentry_sdk
import os
import json
import asyncio
import openai
import anthropic
import instructor


from eve.mongo2 import Document, Collection
from eve.eden_utils import pprint, download_file, image_to_base64
from eve.task import Task
from eve.tool import Tool, get_tools_from_mongo


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
        return ToolCall(
            id=tool_call.id,
            tool=tool_call.name,
            args=tool_call.input,
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


@Collection("threads2")
class Thread(Document):
    name: str
    user: ObjectId
    messages: List[Union[UserMessage, AssistantMessage]] = []

    def update_tool_call(self, message_id, tool_call_index, updates):
        for key, value in updates.items():
            message = next(m for m in self.messages if m.id == message_id)
            setattr(message.tool_calls[tool_call_index], key, value)
        self.update2({
            f"messages.$.tool_call.{k}": v for k, v in updates.items()
        }, filter={"messages.id": message_id})






async def async_anthropic_prompt(messages, system_message, response_model=None, tools={}):
    messages_json = [item for msg in messages for item in msg.anthropic_schema()]

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
    # text_messages = [r.text for r in response.content if r.type == "text" and r.text]
    content = ". ".join([r.text for r in response.content if r.type == "text" and r.text])
    tool_calls = [ToolCall.from_anthropic(r) for r in response.content if r.type == "tool_use"]
    stop = response.stop_reason != "tool_use"
    return content, tool_calls, stop

async def async_openai_prompt(messages, system_message, tools={}):
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
    tool_calls = [ToolCall.from_openai(t) for t in response.message.tool_calls or []]
    stop = response.finish_reason != "tool_calls"
    return content, tool_calls, stop

def anthropic_prompt(messages, system_message, response_model=None, tools={}):
    return asyncio.run(async_anthropic_prompt(messages, system_message, response_model, tools))

def openai_prompt(messages, system_message, tools={}):
    return asyncio.run(async_openai_prompt(messages, system_message, tools))




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


















# thread = Thread.load("6737ab65f27a1cc88397a361", db="STAGE")
# thread = Thread(db="STAGE", name="test575", user=ObjectId(user_id))
# thread.save()
# thread.add_messages(UserMessage(content="can you make a picture of a fancy dog? go for it"), save=True)


# raise Exception("TEST")
async def prompt_thread(
    user_id: str, 
    user_message: UserMessage, 
    thread: Thread, 
    tools: Dict[str, Tool]
):
    thread.push("messages", user_message)

    while True:
        content, tool_calls, stop = await async_anthropic_prompt(
            thread.messages, 
            "You are a helpful assistant.", 
            tools=tools
        )
        assistant_message = AssistantMessage(
            content=content or "",
            tool_calls=tool_calls
        )

        thread.push("messages", assistant_message)
        assistant_message = thread.messages[-1]
        
        for t, tool_call in enumerate(assistant_message.tool_calls):
            tool = tools[tool_call.tool]
            task = await tool.async_start_task(
                user_id, tool_call.args, db="STAGE"
            )
            thread.update_tool_call(assistant_message.id, t, {
                "task": ObjectId(task.id),
                "status": "pending"
            })
            result = await tool.async_wait(task)
            thread.update_tool_call(assistant_message.id, t, result)

        if stop:
            break


async def chat():

    user_id = os.getenv("EDEN_TEST_USER_STAGE")
    tools = get_tools_from_mongo(db="STAGE")
    thread = Thread(db="STAGE", name="test_cli2", user=ObjectId(user_id))
    thread.save()
    
    user_message = UserMessage(content="hello there! who am i?")
    
    await send_message_to_thread(user_id, user_message, thread, tools)



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
    asyncio.run(chat())





# def interactive_chat(args):
#     import asyncio
#     asyncio.run(async_interactive_chat())


# from rich.console import Console
# from rich.progress import Progress, SpinnerColumn, TextColumn


# async def async_interactive_chat():
#     console = Console()
#     thread_id = client.get_or_create_thread("test_thread")
#     print("Thread:", thread_id)

#     while True:
#         try:
#             console.print("[bold yellow]User:\t", end=' ')
#             message_input = input("\033[93m\033[1m")

#             if message_input.lower() == 'escape':
#                 break
            
#             content, metadata, attachments = preprocess_message(message_input)
#             message = {
#                 "content": content,
#                 "metadata": metadata,
#                 "attachments": attachments
#             }
            
#             with Progress(
#                 SpinnerColumn(), 
#                 TextColumn("[bold cyan]"), 
#                 console=console,
#                 transient=True
#             ) as progress:
#                 task = progress.add_task("[cyan]Processing", total=None)

#                 async for response in client.async_chat(message, thread_id):
#                     progress.update(task)
#                     error = response.get("error")
#                     if error:
#                         console.print(f"[bold red]ERROR:\t({error})[/bold red]")
#                         continue
#                     message = json.loads(response.get("message"))
#                     content = message.get("content") or ""
#                     if message.get("tool_calls"):
#                         content += f"{message['tool_calls'][0]['function']['name']}: {message['tool_calls'][0]['function']['arguments']}"
#                     console.print(f"[bold green]Eden:\t{content}[/bold green]")

#         except KeyboardInterrupt:
#             break


# def preprocess_message(message):
#     metadata_pattern = r'\{.*?\}'
#     attachments_pattern = r'\[.*?\]'
#     metadata_match = re.search(metadata_pattern, message)
#     attachments_match = re.search(attachments_pattern, message)
#     metadata = json.loads(metadata_match.group(0)) if metadata_match else {}
#     attachments = json.loads(attachments_match.group(0)) if attachments_match else []
#     clean_message = re.sub(metadata_pattern, '', message)
#     clean_message = re.sub(attachments_pattern, '', clean_message).strip()
#     return clean_message, metadata, attachments

