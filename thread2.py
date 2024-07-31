
"""
X saving messages to threads and yielding them
x CLI / interactive
x actually use tools (and debug/mock mode)
options: final assistant_message or auto
add vision
--
two stage approach
gpt-4v tool
"""

import anthropic
anthropic_client = anthropic.AsyncAnthropic()

from openai.types.chat import ChatCompletion, ChatCompletionMessageToolCall, ChatCompletionFunctionCallOptionParam
import openai
openai_client = openai.AsyncOpenAI()

from pydantic import BaseModel, Field, validator, HttpUrl
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum
import re

from openai.types.chat import ChatCompletion, ChatCompletionMessageToolCall, ChatCompletionFunctionCallOptionParam

import json

from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime



import re
import asyncio

import instructor
import openai
import anthropic
from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, ValidationError
from pydantic.json_schema import SkipJsonSchema
from typing import List, Optional, Dict, Any, Literal, Union
from openai.types.chat import ChatCompletion, ChatCompletionMessageToolCall, ChatCompletionFunctionCallOptionParam

from agent import Agent, get_default_agent
from tool import Tool, get_tools
from mongo import MongoBaseModel, threads
from utils import custom_print

workflows = get_tools("../workflows/public_workflows", exclude=["vid2vid_sd15", "img2vid_museV"])
extra_tools = get_tools("tools")
default_tools = workflows | extra_tools 

anthropic_tools = [t.anthropic_tool_schema() for t in default_tools.values()]
openai_tools = [t.openai_tool_schema() for t in default_tools.values()]




class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    createdAt: datetime = Field(default_factory=datetime.utcnow, exclude=True)
    
    def to_mongo(self):
        data = self.model_dump()
        data["createdAt"] = self.createdAt
        return data


class UserMessage(ChatMessage):
    role: Literal["user"] = "user"
    name: Optional[str] = None
    content: str
    metadata: Optional[Dict[str, Any]] = {}
    attachments: Optional[List[HttpUrl]] = []

    def _get_content(self):
        content = self.content
        if self.attachments:
            content += f"\n\nAttachments: [{', '.join([str(url) for url in self.attachments])}]"
        if self.metadata:
            content += f"\n\nMetadata: {json.dumps(self.metadata)}"
        return content

    def openai_schema(self):
        return [{
            "role": self.role,
            "content": self._get_content(),
            **({"name": self.name} if self.name else {})
        }]

    def anthropic_schema(self):
        return [{
            "role": self.role,
            "content": self._get_content()
        }]
    
    def __str__(self):
        string = f"{(self.name or self.role).capitalize()}:\t\t{self.content}"
        if self.metadata:
            string += f"\t {json.dumps(self.metadata)}" 
        if self.attachments:
            string += f"\t {', '.join(self.attachments)}"
        return custom_print(string, "yellow")


class ToolCall(BaseModel):
    id: str
    name: str
    input: Dict[str, Any]

    @staticmethod
    def from_openai(tool_call):
        return ToolCall(
            id=tool_call.id,
            name=tool_call.function.name,
            input=json.loads(tool_call.function.arguments),
        )
    
    @staticmethod
    def from_anthropic(tool_call):
        return ToolCall(**tool_call.model_dump())
    
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


class ToolResult(BaseModel):
    id: str
    name: str
    result: Optional[str] = None
    error: Optional[str] = None

    def openai_schema(self):
        content = f"Error: {self.error}" if self.error else self.result
        return {
            "role": "tool",
            "name": self.name,
            "content": content,
            "tool_call_id": self.id
        }
    
    def anthropic_schema(self):
        content = f"Error: {self.error}" if self.error else self.result
        return {
            "type": "tool_result",
            "tool_use_id": self.id,
            "content": content
        }


class AssistantMessage(ChatMessage):
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = ""
    tool_calls: Optional[List[ToolCall]] = Field(None, description="Tool calls")
    
    def openai_schema(self):
        schema = [{
            "role": self.role,
            "content": self.content,
            "function_call": None,
            "tool_calls": None
        }]
        if self.tool_calls:
            schema[0]["tool_calls"] = [
                t.openai_schema() for t in self.tool_calls
            ]
        return schema
    
    def anthropic_schema(self):
        schema = [{
            "role": self.role,
            "content": [
                {
                    "type": "text",
                    "text": self.content,
                }
            ],
        }]
        if self.tool_calls:
            schema[0]["content"].extend([
                t.anthropic_schema() for t in self.tool_calls
            ])
        return schema

    def __str__(self):
        string = f"{self.role.capitalize()}:\t{self.content}"
        if self.tool_calls:
            string += f"\t [{', '.join([t.name for t in self.tool_calls])}]"
        return custom_print(string, "green")


class ToolResultMessage(ChatMessage):
    role: Literal["tool"] = "tool"
    tool_results: List[ToolResult]

    def openai_schema(self):
        return [t.openai_schema() for t in self.tool_results]
    
    def anthropic_schema(self):
        return [{
            "role": "user",
            "content": [t.anthropic_schema() for t in self.tool_results]
        }]

    def __str__(self):
        string = ", ".join([
            f"{t.id}:\t\t{t.name} => {t.error or t.result}"
            for t in self.tool_results
        ])
        return custom_print(string, "blue")



class Thread(MongoBaseModel):
    name: str
    user: ObjectId
    messages: List[Union[UserMessage, AssistantMessage, ToolResultMessage]] = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        message_types = {
            "user": UserMessage,
            "assistant": AssistantMessage,
            "tool": ToolResultMessage
        }
        self.messages = [message_types[m.role](**m.model_dump()) for m in self.messages]

    @classmethod
    def from_id(self, document_id: str):
        return super().from_id(self, threads, document_id)

    def to_mongo(self):
        data = super().to_mongo()
        data['messages'] = [m.to_mongo() for m in self.messages]
        data.pop('tools')
        return data

    def save(self):
        super().save(self, threads)

    def update(self, args: dict):
        super().update(self, threads, args)

    def get_messages(self, schema):
        if schema == "openai":
            return [item for m in self.messages for item in m.openai_schema()]
        elif schema == "anthropic":
            return [item for m in self.messages for item in m.anthropic_schema()]




async def openai_prompt(messages):
    while True:
        messages_ = [item for msg in messages for item in msg.openai_schema()]
        print("-----------------")
        print(json.dumps(messages_, indent=4))

        response = await openai_client.chat.completions.create(
            model="gpt-4-turbo",
            tools=openai_tools,
            messages=messages_,
        )

        response = response.choices[0]        
        text_messages = [response.message.content]
        tool_calls = response.message.tool_calls        
        
        if tool_calls:
            tool_calls = [ToolCall.from_openai(tool_call) for tool_call in tool_calls]
        
        assistant_message = AssistantMessage(
            content=text_messages[0] or "",
            tool_calls=tool_calls
        )
        messages.append(assistant_message)

        if tool_calls:
            tool_results = []
            for tool_call in tool_calls:
                if tool_call.name in ["txt2img", "txt2img2", "face_styler", "controlnet", "outpaint", "remix", "inpaint", "background_removal", "moodmix"]:
                    import random
                    idx = random.randint(0, 1000)
                    result = ToolResult(id=tool_call.id, name=tool_call.name, result=f"https://eden.art/results/image_{idx}.jpg")
                    tool_results.append(result)
                    
                elif tool_call.name in ["animate_3D", "txt2vid", "img2vid_museV", "img2vid", "txt2vid_lora", "vid2vid_sd15", "vid2vid_sdxl", "style_mixing", "video_upscaler"]:
                    import random
                    idx = random.randint(0, 1000)
                    tool_result = ToolResult(id=tool_call.id, name=tool_call.name, result=f"https://eden.art/results/video_{idx}.mp4")
                    tool_results.append(tool_result)

                # elif tool_call.name == "get_weather":
                #     tool_call.result = "15 degrees"
                # elif tool_call.name == "convert_temperature":
                #     tool_call.result = "77 degrees"
                # elif tool_call.name == "time":
                #     tool_call.result = "12:44"

            tool_message = ToolResultMessage(tool_results=tool_results)
            messages.append(tool_message)

        
        print("assist",response.finish_reason, assistant_message)
        
        if not response.finish_reason == "tool_calls":
            break
    
    return messages



tool_names = ", ".join([t for t in default_tools])

system_message = """You are a helpful AI named Eve, who knows how to use Eden.

You have the following tools available to you: 
{tool_names}

Please follow these guidelines when responding to the user:
- If you get an error using a tool because the user requested an invalid parameter, or omitted a required parameter, ask the user for clarification before trying again. Do *not* try to guess what the user meant.
- If you get an error using a tool because **YOU** made a mistake, do not apologize for the oversight, just explain what *you* did wrong, fix your mistake, and automatically retry the task.
- When returning the final results to the user, do not include *any* text except a markdown link to the image(s) and/or video(s) with the prompt as the text and the media url as the link. DO NOT include any other text, such as the name of the tool used, a summary of the results, the other args, or any other explanations. Just [prompt](url).
"""
# - When returning the final results to the user, do not summarize or restate the original task or otherwise be verbose. **Only** output the final results in markdown format, with the link to the image(s) and/or video(s).

"""
Todo:
- validate tool_names here
- retry / exponential backoff
"""
async def anthropic_prompt(messages):
    messages_json = [item for msg in messages for item in msg.anthropic_schema()]
    response = await anthropic_client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1024,
        tools=anthropic_tools,
        messages=messages_json,
        system=system_message,
    )
    text_messages = [r.text for r in response.content if r.type == "text"]
    content = text_messages[0] or ""
    tool_calls = [ToolCall.from_anthropic(r) for r in response.content if r.type == "tool_use"]
    stop = response.stop_reason == "tool_use"
    return content, tool_calls, stop


async def process_tool_calls(tool_calls, settings):
    tool_results = []
    for tool_call in tool_calls:
        try:
            input = {k: v for k, v in tool_call.input.items() if v is not None}
            input.update(settings)
            tool = default_tools[tool_call.name]
            updated_args = tool.get_base_model(**input).model_dump()
            result = await tool.async_run(args=updated_args)
            if isinstance(result, list):
                result = ", ".join([r['url'] for r in result])
            result = ToolResult(id=tool_call.id, name=tool_call.name, result=result)
        
        except ValidationError as err:
            errors = [f"{e['loc'][0]}: {e['msg']}" for e in err.errors()]
            errors = ", ".join(errors)
            result = ToolResult(id=tool_call.id, name=tool_call.name, error=errors)

        finally:
            tool_results.append(result)

    return tool_results


async def anthropic_loop(messages, settings):
    while True:
        content, tool_calls, stop = await anthropic_prompt(messages)

        assistant_message = AssistantMessage(
            content=content,
            tool_calls=tool_calls
        )
        yield assistant_message

        if tool_calls:
            tool_results = await process_tool_calls(tool_calls, settings)
            tool_message = ToolResultMessage(tool_results=tool_results)
            yield tool_message
        
        if not stop:
            break
    

async def interactive_chat(initial_message=None):
    user = ObjectId("65284b18f8bbb9bff13ebe65") # user = gene3
    agent = get_default_agent()

    thread = Thread(
        name="my_test_thread1", 
        user=user
    )
    
    while True:
        try:
            if initial_message:
                message_input = initial_message
                initial_message = None
            else:
                message_input = input("\033[93m\033[1m\nUser:\t\t")

            if message_input.lower() == 'escape':
                break
            print("\033[93m\033[1m")
            
            content, metadata, attachments = preprocess_message(message_input)

            user_message = UserMessage(
                content=content,
                metadata=metadata,
                attachments=attachments
            )
            thread.messages.append(user_message)

            settings = user_message.metadata.get("settings", {})

            async for message in anthropic_loop(thread.messages, settings): 
                print(message)
                thread.messages.append(message)

        except KeyboardInterrupt:
            break


def preprocess_message(message):
    metadata_pattern = r'\{.*?\}'
    attachments_pattern = r'\[.*?\]'
    metadata_match = re.search(metadata_pattern, message)
    attachments_matches = re.findall(r'\[(.*?)\]', message)
    
    metadata = json.loads(metadata_match.group(0)) if metadata_match else {}
    
    attachments = []
    for match in attachments_matches:
        urls = match.split(',')
        attachments.extend([url.strip() for url in urls])
    
    clean_message = re.sub(metadata_pattern, '', message)
    clean_message = re.sub(attachments_pattern, '', clean_message).strip()
    
    return clean_message, metadata, attachments


if __name__ == "__main__":
    import asyncio
    asyncio.run(interactive_chat("make a picture of a dog eating a salad, and also at the same time,and convert this attached image to a video"))

