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
import openai
import anthropic
import sentry_sdk

import s3
from agent import Agent
from mongo import MongoBaseModel, get_collection
from config import available_tools
from eden_utils import custom_print, download_file, image_to_base64
from models import Task, User

env = os.getenv("ENV", "STAGE")
sentry_dsn = os.getenv("SENTRY_DSN")

sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=1.0, profiles_sample_rate=1.0)

openai_client = openai.AsyncOpenAI()
anthropic_client = anthropic.AsyncAnthropic()


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

    def openai_schema(self, truncate_images=False):
        return [{
            "role": self.role,
            "content": self._get_content("openai", truncate_images=truncate_images),
            **({"name": self.name} if self.name else {})
        }]

    def anthropic_schema(self, truncate_images=False):
        return [{
            "role": self.role,
            "content": self._get_content("anthropic", truncate_images=truncate_images)
        }]
    
    def __str__(self, truncate_images=False):
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
    
    def validate(self, tools):
        if self.name not in tools:
            raise ToolNotFoundException(self.name)
        tool = tools[self.name]
        input = {k: v for k, v in self.input.items() if v is not None}
        tool.get_base_model(**input)
    
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

    def _get_content(self):
        return f"Error: {self.error}" if self.error else self.result

    def openai_schema(self):
        return {
            "role": "tool",
            "name": self.name,
            "content": self._get_content(),
            "tool_call_id": self.id
        }
    
    def anthropic_schema(self):
        return {
            "type": "tool_result",
            "tool_use_id": self.id,
            "content": self._get_content()
        }


class AssistantMessage(ChatMessage):
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = ""
    tool_calls: Optional[List[ToolCall]] = Field(None, description="Tool calls")
    
    def openai_schema(self, truncate_images=False):
        schema = [{
            "role": self.role,
            "content": self.content,
            "function_call": None,
            "tool_calls": None
        }]
        if self.tool_calls:
            schema[0]["tool_calls"] = [t.openai_schema() for t in self.tool_calls]
        return schema
    
    def anthropic_schema(self, truncate_images=False):
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

    def openai_schema(self, truncate_images=False):
        return [t.openai_schema() for t in self.tool_results]
    
    def anthropic_schema(self, truncate_images=False):
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

import uuid
class Thread(MongoBaseModel):
    name: str
    user: ObjectId
    messages: List[Union[UserMessage, AssistantMessage, ToolResultMessage]] = []
    has_id: bool = Field(False, exclude=True)

    def __init__(self, env, **data):
        if "name" not in data:
            data["name"] = str(uuid.uuid4())
        if isinstance(data["user"], str):
            data["user"] = ObjectId(data["user"])
        print("thread init")
        print(data)
        super().__init__(collection_name="threads", env=env, **data)
        message_types = {
            "user": UserMessage,
            "assistant": AssistantMessage,
            "tool": ToolResultMessage
        }
        self.messages = [message_types[m.role](**m.model_dump()) for m in self.messages]

    @classmethod
    def from_id(self, document_id: str, env: str):
        thread = super().from_id(self, document_id, "threads", env)
        return thread

    @classmethod
    def from_name(self, name: str, user_id: dict, env: str, create_if_missing: bool = False):
        user = User.from_id(user_id, env=env)
        threads = get_collection("threads", env=env)
        thread = threads.find_one({"name": name, "user": user.id})

        if not thread:
            if create_if_missing:
                thread = self(name=name, user=user.id, env=env)
                thread.save()
            else:
                raise Exception(f"Thread {name} not found")
        else:
            if thread["user"] != user.id:
                raise Exception(f"Thread {name} does not belong to user {user.username}")
            thread = self(env=env, **thread)
        return thread

    def to_mongo(self):
        data = super().to_mongo()
        data['messages'] = [m.to_mongo() for m in self.messages]
        return data

    def get_messages(self, schema):
        if schema == "openai":
            return [item for m in self.messages for item in m.openai_schema()]
        elif schema == "anthropic":
            return [item for m in self.messages for item in m.anthropic_schema()]

    def add_messages(self, *new_messages, save=False, reload_messages=False):
        print("add_messages")
        print(self.collection.name)
        if reload_messages and not self.collection is None:
            self.reload_messages()
        print("before extend")
        self.messages.extend(new_messages)
        print("adding messages")
        print(self.messages)
        print("save", save)
        if save:
            print("saving")
            self.save()

    def reload_messages(self):
        self.messages = self.from_id(self.id, env=env).messages


class ToolNotFoundException(Exception):
    def __init__(self, *tool_names): 
        invalid_tools = ", ".join(tool_names)
        super().__init__(f"ToolNotFoundException: {invalid_tools} not found.") 

class UrlNotFoundException(Exception):
    def __init__(self, *urls): 
        invalid_urls = ", ".join(urls)
        super().__init__(f"UrlNotFoundException: {invalid_urls} not found in user messages") 


async def async_anthropic_prompt(messages, system_message, tools):
    messages_json = [item for msg in messages for item in msg.anthropic_schema()]
    anthropic_tools = [t.anthropic_tool_schema(remove_hidden_fields=True, include_tips=True) for t in tools.values()] or None
    response = await anthropic_client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=8192,
        tools=anthropic_tools,
        messages=messages_json,
        system=system_message,
    )
    text_messages = [r.text for r in response.content if r.type == "text"]
    content = text_messages[0] or ""
    tool_calls = [ToolCall.from_anthropic(r) for r in response.content if r.type == "tool_use"]
    stop = response.stop_reason == "tool_use"
    return content, tool_calls, stop


def anthropic_prompt(messages, system_message, tools):
    return asyncio.run(async_anthropic_prompt(messages, system_message, tools))


async def async_openai_prompt(messages, system_message, tools):
    messages_json = [{"role": "system", "content": system_message}]
    messages_json.extend([item for msg in messages for item in msg.openai_schema()])
    openai_tools = [t.openai_tool_schema(remove_hidden_fields=True, include_tips=True) for t in tools.values()] or None
    response = await openai_client.chat.completions.create(
        model="gpt-4-turbo",
        tools=openai_tools,
        messages=messages_json,
    )
    response = response.choices[0]        
    content = response.message.content or ""
    tool_calls = [ToolCall.from_openai(tool_call) for tool_call in response.message.tool_calls or []]
    stop = response.finish_reason == "tool_calls"
    return content, tool_calls, stop


def openai_prompt(messages, system_message, tools):
    return asyncio.run(async_openai_prompt(messages, system_message, tools))


async def process_tool_calls(agent, tool_calls, settings, tools):
    tool_results = []
    for tool_call in tool_calls:
        add_breadcrumb(category="tool_call", data=tool_call.model_dump())
        
        try:
        # if 1:
            tool_call.validate(tools)
            tool = tools[tool_call.name]
            input = {k: v for k, v in tool_call.input.items() if v is not None}
            input.update(settings)        
            updated_args = tool.get_base_model(**input).model_dump()

            if tool.handler == "mongo":
                result = await tool.async_run(updated_args)
                print("the mongo result", result)
            else:
                task = Task(
                    workflow=tool.key,
                    output_type=tool.output_type,
                    args=updated_args,
                    user=agent.owner,
                    env=env
                )
                add_breadcrumb(category="tool_call_task", data=task.model_dump())
                result = await tool.async_submit_and_run(task)

            add_breadcrumb(category="tool_result", data={"result": result})
            result = json.dumps(result)
            result = ToolResult(id=tool_call.id, name=tool_call.name, result=result)

        except ToolNotFoundException as err:
            error = f"Tool {tool_call.name} not found"
            result = ToolResult(id=tool_call.id, name=tool_call.name, error=error)
            capture_exception(err)

        except ValidationError as err:
            errors = [f"{e['loc'][0]}: {e['msg']}" for e in err.errors()]
            errors = ", ".join(errors)
            result = ToolResult(id=tool_call.id, name=tool_call.name, error=errors)
            capture_exception(err)

        except Exception as err:
            error = f"An internal error occurred: {err}"
            result = ToolResult(id=tool_call.id, name=tool_call.name, error=error)
            capture_exception(err)

        finally:
            tool_results.append(result)

    return tool_results


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

        try:
        # if 1:
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
            valid_urls += [
                            url 
                            for m in messages if type(m) == ToolResultMessage 
                            for result in m.tool_results if result and result.result 
                            for entry in result.result if isinstance(entry, dict) and 'filename' in entry
                            for url in re.findall(url_pattern, entry['filename'])
                        ]

            tool_calls_urls = re.findall(url_pattern, ";".join([json.dumps(tool_call.input) for tool_call in tool_calls]))
            invalid_urls = [url for url in tool_calls_urls if url not in valid_urls]
            if invalid_urls:
                add_breadcrumb(category="invalid_urls", data={"invalid": invalid_urls, "valid": valid_urls})
                raise UrlNotFoundException(*invalid_urls)
                
            return content, tool_calls, stop

        # if there are still hallucinations after max_attempts, just let the LLM deal with it
        except (ToolNotFoundException, UrlNotFoundException) as e:
            if num_attempts == max_attempts:
                return content, tool_calls, stop





async def async_prompt(
    thread: Thread,
    agent: Agent,
    user_message: UserMessage,
    provider: Literal["anthropic", "openai"] = "anthropic",
    auto_save: bool = True
):
    tools = {k: v for k, v in available_tools.items() if k in agent.tools}
    settings = user_message.metadata.get("settings", {})
    system_message = agent.get_system_message()

    data = user_message.model_dump().update({"attachments": user_message.attachments, "settings": settings, "agent": agent.id})
    add_breadcrumb(category="prompt", data=data)

    # upload all attachments to s3
    attachments = user_message.attachments or []    
    for a, attachment in enumerate(attachments):
        if not attachment.startswith(s3.get_root_url(env=env)):
            attachment_url, _ = s3.upload_file_from_url(attachment, env=env)
            attachments[a] = attachment_url
    user_message.attachments = attachments
    if user_message.attachments:
        add_breadcrumb(category="attachments", data=user_message.attachments)

    # get message buffer starting from the 5th last UserMessage
    user_messages = [i for i, msg in enumerate(thread.messages) if isinstance(msg, UserMessage)]
    start_index = user_messages[-5] if len(user_messages) >= 5 else 0
    thread_messages = thread.messages[start_index:]
    new_messages = [user_message]

    data = {"messages": [m.model_dump() for m in thread_messages]}
    add_breadcrumb(category="thread_messages", data=data)

    while True:
        messages = thread_messages + new_messages

        try:   
        # if 1:
            content, tool_calls, stop = await prompt_llm_and_validate(
                messages, system_message, provider, tools
            )
            data = {"content": content, "tool_calls": [t.model_dump() for t in tool_calls], "stop": stop}
            add_breadcrumb(category="llm_response", data=data)

        except Exception as err:
            capture_exception(err)
            assistant_message = AssistantMessage(
                content="I'm sorry but something went wrong internally. Please try again later.",
                tool_calls=None
            )
            yield assistant_message
            return
        
        assistant_message = AssistantMessage(
            content=content,
            tool_calls=tool_calls
        )
        new_messages.append(assistant_message)
        yield assistant_message
        
        if tool_calls:
            tool_results = await process_tool_calls(agent, tool_calls, settings, tools)
            add_breadcrumb(category="tool_results", data={"tool_results": [t.model_dump() for t in tool_results]})
            tool_message = ToolResultMessage(tool_results=tool_results)
            new_messages.append(tool_message)
            yield tool_message

        if not stop:
            break

    if auto_save:
        thread.add_messages(*new_messages, save=True, reload_messages=True)


def prompt(
    thread: Thread,
    agent: Agent,
    user_message: UserMessage,
    provider: Literal["anthropic", "openai"] = "anthropic",
    auto_save: bool = True
):
    async def async_wrapper():
        return [message async for message in async_prompt(
            thread, agent, user_message, provider, auto_save
        )]
    return asyncio.run(async_wrapper())


async def interactive_chat(initial_message=None):
    user_id = ObjectId("65284b18f8bbb9bff13ebe65") # user = gene3
    agent = Agent.from_id("66f1c7b5ee5c5f46bbfd3cb9", env=env)

    # thread = Thread(
    #     name="my_test_interactive_thread", 
    #     user=user,
    #     env=env
    # )
    thread = Thread.from_name(
        name="my_test_interactive_thread",
        user_id=user_id,
        env=env, 
        create_if_missing=True
    )
    
    while True:
        try:
        # if 1:
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

            async for message in async_prompt(thread, agent, user_message): 
                print(message)

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


def pretty_print_messages(messages, schema: Literal["anthropic", "openai"] = "openai"):
    if schema == "anthropic":
        messages = [item for msg in messages for item in msg.anthropic_schema(truncate_images=True)]
    elif schema == "openai":
        messages = [item for msg in messages for item in msg.openai_schema(truncate_images=True)]
    json_str = json.dumps(messages, indent=4)
    print(json_str)


if __name__ == "__main__":
    import asyncio
    asyncio.run(interactive_chat()) 
