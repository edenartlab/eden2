import asyncio
import json
import instructor
import openai
from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl
from pydantic.json_schema import SkipJsonSchema
from typing import List, Optional, Dict, Any, Literal, Union
from openai.types.chat import ChatCompletion, ChatCompletionMessageToolCall, ChatCompletionFunctionCallOptionParam

from endpoint import tools, endpoint_summary

default_system_message = (
    "You are an assistant who is an expert at using Eden. "
    "You have the following tools available to you. "
    "\n\n{endpoint_summary}."
    "\n\nIf the user clearly wants you to make something, select one of the tools. "
    "If you are not sure, or the user is just making chat with you or asking a question, leave the tool null and just respond through the chat message. "
    "If you're not sure, you can leave it blank and ask the user for clarification or confirmation. "
    "Look through the whole conversation history for clues as to what the user wants. If they are referencing previous outputs, make sure to use them."
)


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, values, **kwargs):
        if not ObjectId.is_valid(v):
            raise ValueError('Invalid ObjectId')
        return ObjectId(v)
    
    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema):
        field_schema.update(type='string')


class MongoBaseModel(BaseModel):
    id: SkipJsonSchema[PyObjectId] = Field(default_factory=ObjectId, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            ObjectId: str,
            HttpUrl: str
        }
        populate_by_name = True

    @classmethod
    def from_mongo(cls, data: dict):
        return cls(**data)

    def to_mongo(self):
        data = self.model_dump()
        data["_id"] = data.pop("id")
        data["created_at"] = self.created_at
        return data

    @classmethod
    def save(cls, document, collection):
        data = document.to_mongo()
        document_id = data.get('_id')
        if document_id:
            return collection.update_one({'_id': document_id}, {'$set': data}, upsert=True)
        else:
            return collection.insert_one(data)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
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
        return f"\033[93m\033[1mAI\t\033[22moutput: {self.content}\033[0m"


def generate_fake_jpg_filename():
    import uuid
    return f"/tmp/{uuid.uuid4()}.jpg"


class Thread(MongoBaseModel):
    messages: List[Union[UserMessage, AssistantMessage, SystemMessage, ToolMessage]] = []
    metadata: Optional[Dict[str, str]] = Field({}, description="Preset settings, metadata, or context information")
    system_message: str = Field(..., description="You are an Eden team member who is an expert at using Eden.")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        messages = []
        for m in self.messages:
            if m.role == "user" and not isinstance(m, UserMessage):
                m = UserMessage(**m.model_dump())
            elif m.role == "assistant" and not isinstance(m, AssistantMessage):
                m = AssistantMessage(**m.model_dump())
            elif m.role == "system" and not isinstance(m, SystemMessage):
                m = SystemMessage(**m.model_dump())
            elif m.role == "tool" and not isinstance(m, ToolMessage):
                m = ToolMessage(**m.model_dump())
            messages.append(m)
        self.messages = messages

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
            tools=[t.tool_schema() for t in tools.values()]
        )
        message = response.choices[0].message
        assistant_message = AssistantMessage(**message.model_dump())
        
        self.add_message(assistant_message)
        yield assistant_message
        
        tool_calls = message.tool_calls
        if tool_calls:
            tool_name = tool_calls[0].function.name
            args = json.loads(tool_calls[0].function.arguments)
            tool = tools[tool_name]
            result = await tool.execute(
                workflow=tool_name, 
                config=args
            )
            content = result.get("urls")
            if isinstance(content, list):
                content = ", ".join(content)
            tool_message = ToolMessage(
                name=tool_calls[0].function.name,
                tool_call_id=tool_calls[0].id,
                content=content
            )
            self.add_message(tool_message)
            yield tool_message


async def maybe_use_tool(
    messages: List[Union[UserMessage, AssistantMessage, SystemMessage, ToolMessage]],
    tools: List[dict] = None,
    model: str = "gpt-4-1106-preview",
) -> List[ChatMessage]:
    client = instructor.from_openai(openai.AsyncOpenAI())
    response = await client.chat.completions.create(
        model=model,
        response_model=None,
        tools=tools,
        messages=messages,
    )
    return response


def preprocess_message(message):
    import re
    metadata_pattern = r'\{.*?\}'
    attachments_pattern = r'\[.*?\]'
    metadata_match = re.search(metadata_pattern, message)
    attachments_match = re.search(attachments_pattern, message)
    metadata = json.loads(metadata_match.group(0)) if metadata_match else {}
    attachments = json.loads(attachments_match.group(0)) if attachments_match else []
    clean_message = re.sub(metadata_pattern, '', message)
    clean_message = re.sub(attachments_pattern, '', clean_message).strip()
    return clean_message, metadata, attachments


def interactive_chat():
    session = Thread(system_message=default_system_message)
    while True:
        try:
            message_input = input("\033[92m\033[1mUser: \t")
            if message_input.lower() == 'escape':
                break
            content, metadata, attachments = preprocess_message(message_input)
            user_message = UserMessage(
                content=content,
                metadata=metadata,
                attachments=attachments
            )
            print("\033[A\033[K", end='')  # Clears the input line
            print(user_message)
            responses = session.prompt(user_message)
            for response in responses:
                print(response)
            
        except KeyboardInterrupt:
            break

        
if __name__ == "__main__":
    interactive_chat()
