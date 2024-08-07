import re
import asyncio
import json
import instructor
import openai
import anthropic
from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, ValidationError
from typing import List, Optional, Dict, Any, Literal, Union
from openai.types.chat import ChatCompletionMessageToolCall, ChatCompletionFunctionCallOptionParam

from agent import Agent, get_default_agent
from tool import Tool, get_tools
from mongo import MongoBaseModel, threads

workflows = get_tools("../workflows/public_workflows", exclude=["vid2vid_sd15", "img2vid_museV"])
private_workflows = get_tools("../workflows/private_workflows", exclude=["beeple_ai", "xhibit/vton", "xhibit/remix"])
extra_tools = get_tools("tools")
default_tools = workflows | extra_tools 


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    createdAt: datetime = Field(default_factory=datetime.utcnow, exclude=True)
    
    def to_mongo(self, **kwargs):
        data = self.model_dump()
        data["createdAt"] = self.createdAt
        return data


class SystemMessage(ChatMessage):
    role: Literal["system"] = "system"
    content: str

    def chat_message(self):
        return {
            "role": self.role,
            "content": self.content,
        }

    def __str__(self):
        return f"\033[91m\033[1m{self.role.capitalize()}\t\033[22m{self.content}\033[0m"


class UserMessage(ChatMessage):
    role: Literal["user"] = "user"
    name: Optional[str] = Field(None, description="The name of the user")
    content: str = Field(..., description="A chat message")
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
        # if self.metadata:
            # content += f"\n\nMetadata: {self.metadata.json()}"
        if self.attachments:
            attachments_str = '", "'.join([str(url) for url in self.attachments])
            content += f'\n\nAttachments: ["{attachments_str}"]'
        message = {
            "role": self.role,
            "content": content,
        }
        if self.name:
            message["name"] = self.name
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
    tool_calls: Optional[List[ChatCompletionMessageToolCall]] = Field(None, description="Available tools")

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
            functions = [f"{tc.function.name}: {tc.function.arguments}" for tc in self.tool_calls]
            tool_call_str = "\n".join(functions)            
        else:
            tool_call_str = ""
        return f"\033[93m\033[1mAI\t\033[22m{content_str}{tool_call_str}\033[0m"


class AssistantThought(ChatMessage):
    role: Literal["assistant"] = "assistant"
    content: str

    def chat_message(self):
        return {
            "role": self.role,
            "content": f"Thought: {self.content}",
        }

    def __str__(self):
        return f"\033[94m\033[1m{self.role.capitalize()}\t\033[22mThought: {self.content}\033[0m"


class ToolMessage(ChatMessage):
    role: Literal["tool"] = "tool"
    name: str = Field(..., description="The name of the tool")
    content: str = Field(None, description="A chat message to send back to the user. If you are using a tool, say which one. If you are not using a tool, just chat back to the user, don't parrot back their message.")
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
    name: str
    user: ObjectId
    messages: List[Union[SystemMessage, UserMessage, AssistantMessage, AssistantThought, ToolMessage]] = []
    metadata: Optional[Dict[str, str]] = Field({}, description="Preset settings, metadata, or context information")
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
        
        # todo: should tools always be defaults or saved to thread
        self.tools = default_tools

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

    def get_chat_messages(self, system_message: str = None, include_thoughts=False):
        system_message = SystemMessage(content=system_message)        
        messages = self.messages if include_thoughts else [
            m for m in self.messages if not isinstance(m, AssistantThought)
        ] 
        messages = [system_message, *messages]
        return [m.chat_message() for m in messages]

    def add_message(self, *messages: ChatMessage):
        self.messages.extend(messages)
        self.save()
    
    async def prompt(
        self, 
        agent: Agent,
        user_message: UserMessage,
    ):
        self.add_message(user_message)  
        system_message = agent.get_system_message(self.tools)
        
        """
        This block tries three times to generate a valid response.
        An invalid response is one that calls a hallucinated tool.
        A valid response calls a valid tool or no tool.        
        """
        valid_response = False
        num_attempts = 0
        while not valid_response and num_attempts < 3:
            response = await prompt(
                self.get_chat_messages(system_message=system_message),
                tools=[t.tool_schema() for t in self.tools.values()]
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls
            if not tool_calls:
                """
                No tool calls, so just return the assistant message and terminate.
                """
                assistant_message = AssistantMessage(**message.model_dump())
                self.add_message(assistant_message)
                yield assistant_message
                return

            print("tool calls", tool_calls[0])
            args = json.loads(tool_calls[0].function.arguments)
            tool_name = tool_calls[0].function.name
            tool = self.tools.get(tool_name)

            if tool:
                valid_response = True
            else:
                num_attempts += 1
                if num_attempts == 3:
                    assistant_message = AssistantMessage(
                        content="Sorry, failed to find a suitable tool. Please try to modify your request or try again later."
                    )
                    self.add_message(assistant_message)
                    yield assistant_message
                    return

        """
        The rest of the function is for handling an assistant message that calls a tool.
        This try-except block first checks if the tool parameters are valid.
        If they are not, it generates a helpful response explaining the problem.
        """
        try:
            extra_args = user_message.metadata.get('settings', {})
            args = {k: v for k, v in args.items() if v is not None}
            args.update(extra_args)
            print("args", args)
            updated_args = tool.get_base_model(**args).model_dump()
            print("updated ars", updated_args)

        except ValidationError as err:
            """
            This exception only happens when the tool call parameters are invalid.
            We generate a helpful error message for the user indicating the invalid parameters.
            """
            assistant_message = AssistantMessage(**message.model_dump())
            yield assistant_message

            error_details = "\n".join([f" - {e['loc'][0]}: {e['msg']}" for e in err.errors()])
            error_message = f"{tool_name}: {args} failed with errors:\n{error_details}"
            print("error message", error_message)
            tool_message = ToolMessage(
                name=tool_calls[0].function.name,
                tool_call_id=tool_calls[0].id,
                content=error_message
            )
            self.add_message(assistant_message, tool_message)

            system_message_help = f"You are an expert at using Eden. You have conversations with users in which they sometimes request for you to use the tool {tool_name}. Sometimes you invoke the tool but it fails with one or more errors, which you report. Given the conversation (especially the user's last message requesting the tool), and the error message, you should either explain the problem to the user and/or ask for clarification to try again. For context, the following is a summary of {tool_name}:\n\n{tool.summary()}"
            messages = self.get_chat_messages(system_message=system_message_help).copy()
            error_message = await prompt(messages)
            tool_message.content = error_message.choices[0].message.content
            yield tool_message
            return
        
        """
        The tool call is valid, so we can proceed with the tool call.
        Occasionally, multiple tool calls are made. Right now we only handle one.
        Todo: actually handle multiple tool calls
        """
        if len(message.tool_calls) > 1:
            print("Multiple tool calls found, only using the first one", message.tool_calls)
            message.tool_calls = [message.tool_calls[0]]
        
        message.tool_calls[0].function.arguments = json.dumps(updated_args)
        assistant_message = AssistantMessage(**message.model_dump())
        yield assistant_message
        
        # run the tool
        result = await tool.async_run(
            args=updated_args
        )

        # if the tool fails to run, return an error message and do not save the assistant or tool messages
        if not result:
            assistant_message = AssistantMessage(
                content="Sorry, the tool failed to run. Please try again or modify your prompt."
            )
            yield assistant_message
            return

        if isinstance(result, list):
            result = ", ".join([r['url'] for r in result])

        # tool message contains the result of the tool call
        tool_message = ToolMessage(
            name=tool_calls[0].function.name,
            tool_call_id=tool_calls[0].id,
            content=result
        )

        self.add_message(assistant_message, tool_message)
        yield tool_message




async def prompt(
    messages: List[Union[UserMessage, AssistantMessage, SystemMessage, ToolMessage]],
    tools: List[dict] = None,
    model: str = "gpt-4-turbo"
) -> ChatMessage: 
    client = instructor.from_openai(
        openai.AsyncOpenAI(), 
        mode=instructor.Mode.TOOLS
    )
    response = await client.chat.completions.create(
        model=model,
        response_model=None,
        tools=tools,
        messages=messages,
        max_retries=2,
    )
    # todo: deal with tool hallucination
    return response


def get_thread(name: str, user: dict, create_if_missing: bool = False):
    thread = threads.find_one({"name": name, "user": user["_id"]})
    if not thread:
        if create_if_missing:
            thread = Thread(name=name, user=user["_id"])
            thread.save()
        else:
            raise Exception(f"Thread {name} not found")
    else:
        thread = Thread(**thread)
    return thread


async def interactive_chat():
    user = ObjectId("65284b18f8bbb9bff13ebe65") # user = gene3
    agent = get_default_agent() # eve
    tools = get_tools("../workflows/public_workflows", exclude=["xhibit/remix", "xhibit/vton", "blend"])

    thread = Thread(
        name="my_test_thread", 
        user=user,
        tools=tools
    )
    
    while True:
        try:
            message_input = "this is a thing [http://nhl.com]" #input("\033[92m\033[1mUser:\t")
            if message_input.lower() == 'escape':
                break
            
            content, metadata, attachments = preprocess_message(message_input)
            user_message = UserMessage(
                content=content,
                metadata=metadata,
                attachments=attachments
            )
            print("\033[93m\033[1m")
            async for msg in thread.prompt(agent, user_message):
                print(msg)

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
    print("clean message", clean_message)
    print("metadata", metadata)
    print("attachments", attachments)   
    return clean_message, metadata, attachments


if __name__ == "__main__":
    import asyncio
    asyncio.run(interactive_chat())





# async_create?
async def anthropic_prompt(
    messages: List[Union[UserMessage, AssistantMessage, SystemMessage, ToolMessage]],
    response_model = BaseModel,
    model: str = "claude-3-5-sonnet-20240620"
) -> ChatMessage: 
    client = instructor.from_anthropic(
        anthropic.Anthropic(),
    )
    response = client.messages.create(
        model=model,
        response_model=response_model,
        messages=messages,
        max_tokens=1024,
        max_retries=5,
    )
    return response


async def openai_prompt(
    messages: List[Union[UserMessage, AssistantMessage, SystemMessage, ToolMessage]],
    response_model = BaseModel,
    model: str = "gpt-4-turbo"
) -> ChatMessage: 
    client = instructor.from_openai(
        openai.AsyncOpenAI(), 
        mode=instructor.Mode.TOOLS
    )
    response = await client.chat.completions.create(
        model=model,
        response_model=response_model,
        messages=messages,
        max_retries=5,
    )
    return response
