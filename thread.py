import re
import asyncio
import json
import instructor
import openai
from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, ValidationError
from pydantic.json_schema import SkipJsonSchema
from typing import List, Optional, Dict, Any, Literal, Union
from openai.types.chat import ChatCompletion, ChatCompletionMessageToolCall, ChatCompletionFunctionCallOptionParam

from tools import Tool, get_tools, get_tools_summary
from mongo import MongoBaseModel


default_tools = get_tools("../workflows") | get_tools("tools")

default_system_message = (
    "You are an assistant who is an expert at using Eden. "
    "You have the following tools available to you: "
    "\n\n---\n{tools_summary}\n---"
    "\n\nIf the user clearly wants you to make something, select exactly ONE of the tools. Do NOT select multiple tools. Do NOT hallucinate any tool, especially do not use 'multi_tool_use' or 'multi_tool_use.parallel.parallel'. Only tools allowed: {tool_names}." 
    "If the user is just making chat with you or asking a question, leave the tool null and just respond through the chat message. "
    "If you're not sure of the user's intent, you can select no tool and ask the user for clarification or confirmation. " 
    "Look through the whole conversation history for clues as to what the user wants. If they are referencing previous outputs, make sure to use them."
).format(
    tools_summary=get_tools_summary(default_tools), 
    tool_names=', '.join([t for t in default_tools])
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    created_at: datetime = Field(default_factory=datetime.utcnow, exclude=True)
    
    def to_mongo(self, **kwargs):
        data = self.model_dump()
        data["created_at"] = self.created_at
        return data


class SystemMessage(ChatMessage):
    role: Literal["system"] = "system"
    content: Optional[str] = default_system_message

    def chat_message(self):
        return {
            "role": self.role,
            "content": self.content,
        }

    def __str__(self):
        return f"\033[91m\033[1m{self.role.capitalize()}\t\033[22m{self.content}\033[0m"


class UserMessage(ChatMessage):
    role: Literal["user"] = "user"
    name: Optional[str] = Field(None, description="The name of the tool")
    content: Optional[str] = Field(None, description="A chat message")
    metadata: Optional[Dict[str, Any]] = Field({}, description="Preset settings, metadata, or context information")
    attachments: Optional[List[HttpUrl]] = Field([], description="Attached files included")

    def __init__(self, **data):
        super().__init__(**data)
        if self.name:
            self.name = ''.join(re.findall(r'[a-zA-Z0-9_-]+', self.name))

    def to_mongo(self):
        data = super().to_mongo()
        data['attachments'] = [str(url) for url in self.attachments]
        return data
    
    def chat_message(self):
        content = self.content
        if self.metadata:
            content += f"\n\nMetadata: {self.metadata.json()}"
        if self.attachments:
            attachments_str = '", "'.join([str(url) for url in self.attachments])
            content += f'\n\nAttachments: ["{attachments_str}"]'
        message = {
            "role": self.role,
            "name": self.name,
            "content": content,
        } if self.name else {
            "role": self.role,
            "content": content,
        }
        return message

    def __str__(self):
        attachments = [str(url) for url in self.attachments]
        attachments_str = ", ".join(attachments)
        attachments_str = f"\n\tAttachments: [{attachments_str}]" if attachments_str else ""
        metadata_str = f"\n\tMetadata: {json.dumps(self.metadata)}" if self.metadata else ""
        return f"\033[92m\033[1mUser\t\033[22m{self.content}{metadata_str}{attachments_str}\033[0m"


class AssistantMessage(ChatMessage):
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = "You are an expert at using Eden."
    function_call: Optional[ChatCompletionFunctionCallOptionParam] = None
    tool_calls: Optional[List[ChatCompletionMessageToolCall]] = Field([], description="Available tools")

    def chat_message(self):
        return {
            "role": self.role,
            "content": self.content,
            "function_call": self.function_call,
            "tool_calls": self.tool_calls,
        }

    def __str__(self):
        content_str = f"{self.content}\n" if self.content else ""
        if self.tool_calls:
            function = self.tool_calls[0].function
            tool_call_str = f"{function.name}: {function.arguments}"
        else:
            tool_call_str = ""
        return f"\033[93m\033[1mAI\t\033[22m{content_str}{tool_call_str}\033[0m"


class ToolMessage(ChatMessage):
    role: Literal["tool"] = "tool"
    name: Optional[str] = Field(..., description="The name of the tool")
    content: Optional[str] = Field(None, description="A chat message to send back to the user. If you are using a tool, say which one. If you are not using a tool, just chat back to the user, don't parrot back their message.")
    tool_call_id: Optional[str] = Field(None, description="The id of the tool call")

    def chat_message(self):
        return {
            "role": self.role,
            "name": self.name,
            "content": self.content,
            "tool_call_id": self.tool_call_id,
        }
    
    def __str__(self):
        return f"\033[93m\033[1mAI\t\033[22m:{self.content}\033[0m"


class Thread(MongoBaseModel):
    messages: List[Union[UserMessage, AssistantMessage, SystemMessage, ToolMessage]] = []
    metadata: Optional[Dict[str, str]] = Field({}, description="Preset settings, metadata, or context information")
    system_message: str = Field(default_system_message, description="You are an Eden team member who is an expert at using Eden.")
    tools: Dict[str, Tool] = Field(default_tools, description="Tools available to the user")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        message_types = {
            "user": UserMessage,
            "assistant": AssistantMessage,
            "system": SystemMessage,
            "tool": ToolMessage
        }
        self.messages = [message_types[m.role](**m.model_dump()) for m in self.messages]
        # self.tools = kwargs.get('tools', default_tools)
        # self.system_message = kwargs.get('system_message', default_system_message)

    def to_mongo(self):
        data = super().to_mongo()
        data['messages'] = [m.to_mongo() for m in self.messages]
        return data

    def get_chat_messages(self, system_message: str = None):
        system_message = SystemMessage(
            content=system_message or self.system_message
        )
        messages = [system_message, *self.messages]
        return [m.chat_message() for m in messages]

    def add_message(self, message: ChatMessage):
        self.messages.append(message)

    async def prompt(
        self, 
        user_message: UserMessage,
        system_message: Optional[str] = None
    ):
        self.add_message(user_message)
        response = await maybe_use_tool(
            self.get_chat_messages(system_message=system_message),
            tools=[t.tool_schema() for t in self.tools.values()]
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls
        if not tool_calls:
            assistant_message = AssistantMessage(**message.model_dump())
            self.add_message(assistant_message)
            yield assistant_message
            return  # no tool calls, we're done here

        args = json.loads(tool_calls[0].function.arguments)
        tool_name = tool_calls[0].function.name
        tool = self.tools.get(tool_name)

        if tool is None:
            raise Exception(f"Tool {tool_name} not found")

        try:
            args = {k: v for k, v in args.items() if v is not None}
            updated_args = tool.BaseModel(**args).model_dump() 

        except ValidationError as err:            
            assistant_message = AssistantMessage(**message.model_dump())
            yield assistant_message

            error_details = "\n".join([f" - {e['loc'][0]}: {e['msg']}" for e in err.errors()])
            error_message = f"{tool_name}: {args} failed with errors:\n{error_details}"

            tool_message = ToolMessage(
                name=tool_calls[0].function.name,
                tool_call_id=tool_calls[0].id,
                content=error_message
            )
            self.add_message(assistant_message)
            self.add_message(tool_message)

            system_message_help = f"You are an expert at using Eden. You have conversations with users in which they sometimes request for you to use the tool {tool_name}. Sometimes you invoke the tool but it fails with one or more errors, which you report. Given the conversation (especially the user's last message requesting the tool), and the error message, you should either explain the problem to the user and/or ask for clarification to try again. For context, the following is a summary of {tool_name}:\n\n{tool.summary()}"
            messages = self.get_chat_messages(system_message=system_message_help).copy()
            error_message = await chat(messages)
            tool_message.content = error_message.choices[0].message.content
            yield tool_message
            return
        

        # should we use updated_args or args in the assistant message?
        message.tool_calls[0].function.arguments = json.dumps(updated_args)

        assistant_message = AssistantMessage(**message.model_dump())
        
        yield assistant_message
        
        result = await tool.execute(
            workflow=tool_name, 
            config=updated_args
        )
        print(result)
        # content = result #result.get("urls")
        # todo: check for errors
        if isinstance(result, list):
            result = ", ".join(result)

        tool_message = ToolMessage(
            name=tool_calls[0].function.name,
            tool_call_id=tool_calls[0].id,
            content=result
        )

        self.add_message(assistant_message)
        self.add_message(tool_message)
        yield tool_message


async def maybe_use_tool(
    messages: List[Union[UserMessage, AssistantMessage, SystemMessage, ToolMessage]],
    tools: List[dict] = None,
    model: str = "gpt-4-1106-preview",
) -> ChatMessage:
    client = instructor.from_openai(openai.AsyncOpenAI(), mode=instructor.Mode.TOOLS)
    response = await client.chat.completions.create(
        model=model,
        response_model=None,
        tools=tools,
        messages=messages,
        max_retries=2,
    )
    return response


async def chat(
    messages: List[Union[UserMessage, AssistantMessage, SystemMessage, ToolMessage]],
    model: str = "gpt-4-1106-preview",
) -> ChatMessage: 
    client = instructor.from_openai(openai.AsyncOpenAI(), mode=instructor.Mode.TOOLS)
    response = await client.chat.completions.create(
        model=model,
        response_model=None,
        messages=messages,
        max_retries=2,
    )
    return response
