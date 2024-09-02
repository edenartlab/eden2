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
from agent import Agent, get_default_agent
from tool import get_tools, get_comfyui_tools
from mongo import MongoBaseModel, mongo_client, envs
from utils import custom_print, download_file, file_to_base64_data
from models import Task


env = os.getenv("ENV", "STAGE")
sentry_dsn = os.getenv("SENTRY_DSN")

sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=1.0, profiles_sample_rate=1.0)

eve_tools = [
    "txt2img", "flux", "img2img", "controlnet", "layer_diffusion", "remix", "inpaint", "outpaint", "background_removal", "background_removal_video", "storydiffusion", "clarity_upscaler", "face_styler", "upscaler",
    "animate_3D", "txt2vid",  "img2vid", "vid2vid_sdxl", "style_mixing", "video_upscaler", 
    "stable_audio", "audiocraft", "reel",
    "lora_trainer",
]

default_tools = get_comfyui_tools("../workflows/workspaces") | get_tools("tools")
if env == "PROD":
    default_tools = {k: v for k, v in default_tools.items() if k in eve_tools}

anthropic_tools = [t.anthropic_tool_schema(remove_hidden_fields=True) for t in default_tools.values()]
openai_tools = [t.openai_tool_schema(remove_hidden_fields=True) for t in default_tools.values()]

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
            print("attachments", self.attachments)
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
                        "data": file_to_base64_data(file_path, max_size=512, quality=95, truncate=truncate_images)
                    }
                } for file_path in attachment_files]
            elif schema == "openai":
                content = [{
                    "type": "image_url", 
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{file_to_base64_data(file_path, max_size=512, quality=95, truncate=truncate_images)}"
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
    
    def validate(self):
        if self.name not in default_tools:
            raise ToolNotFoundException(self.name)
        tool = default_tools[self.name]
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


class Thread(MongoBaseModel):
    name: str
    user: ObjectId
    messages: List[Union[UserMessage, AssistantMessage, ToolResultMessage]] = []
    has_id: bool = Field(False, exclude=True)

    def __init__(self, env, **data):
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
    def from_name(self, name: str, user: dict, env: str, create_if_missing: bool = False):
        db_name = envs[env]["db_name"]
        threads = mongo_client[db_name]["threads"]
        thread = threads.find_one({"name": name, "user": user["_id"]})

        if not thread:
            if create_if_missing:
                thread = self(name=name, user=user["_id"], env=env)
                thread.save()
            else:
                raise Exception(f"Thread {name} not found")
        else:
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
        if reload_messages and not self.collection is None:
            self.reload_messages()
        self.messages.extend(new_messages)
        if save:
            self.save()

    def reload_messages(self):
        self.messages = self.from_id(self.id, env=env).messages


class ToolNotFoundException(Exception):
    def __init__(self, *tool_names): 
        invalid_tools, available_tools = ", ".join(tool_names), ", ".join(default_tools.keys())
        super().__init__(f"ToolNotFoundException: {invalid_tools} not found. Tools available: {available_tools}") 

class UrlNotFoundException(Exception):
    def __init__(self, *urls): 
        invalid_urls = ", ".join(urls)
        super().__init__(f"UrlNotFoundException: {invalid_urls} not found in user messages") 


async def anthropic_prompt(messages, system_message):
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


async def openai_prompt(messages, system_message):
    messages_json = [{"role": "system", "content": system_message}]
    messages_json.extend([item for msg in messages for item in msg.openai_schema()])
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


async def process_tool_calls(tool_calls, settings):
    tool_results = []
    for tool_call in tool_calls:
        add_breadcrumb(category="tool_call", data=tool_call.model_dump())
        
        try:
            tool_call.validate()
            tool = default_tools[tool_call.name]
            input = {k: v for k, v in tool_call.input.items() if v is not None}
            input.update(settings)
            updated_args = tool.get_base_model(**input).model_dump()
            print("updated args", updated_args)

            task = Task(
                workflow=tool.key,
                output_type=tool.output_type,
                args=updated_args,
                user=ObjectId("65284b18f8bbb9bff13ebe65"),
                env=env
            )
            add_breadcrumb(category="tool_call_task", data=task.model_dump())
            
            result = await tool.async_submit_and_run(task)

            #TODO: result should give us the url for all endpoints
            # works for comfy, not modal. result["result"]
            add_breadcrumb(category="tool_result", data={"result": result})

            if isinstance(result, list):
                result = ", ".join([r['url'] for r in result])

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
async def prompt_llm_and_validate(messages, system_message, provider):
    num_attempts, max_attempts = 0, 3
    while num_attempts < max_attempts:
        num_attempts += 1 
        pretty_print_messages(messages, schema=provider)

        try:
            if provider == "anthropic":
                content, tool_calls, stop = await anthropic_prompt(messages, system_message)
            elif provider == "openai":
                content, tool_calls, stop = await openai_prompt(messages, system_message)
            
            # check for hallucinated tools
            invalid_tools = [t.name for t in tool_calls if not t.name in default_tools]
            if invalid_tools:
                add_breadcrumb(category="invalid_tools", data={"invalid": invalid_tools})
                raise ToolNotFoundException(*invalid_tools)

            # check for hallucinated urls
            #url_pattern = r'https://(?:eden|edenartlab-stage-data)\.s3\.amazonaws\.com/\S+\.(?:jpg|jpeg|png|gif|bmp|webp|mp4|mp3|wav|aiff)'
            url_pattern = r'https://(?:eden|edenartlab-stage-(?:data|prod))\.s3\.amazonaws\.com/\S+\.(?:jpg|jpeg|png|gif|bmp|webp|mp4|mp3|wav|aiff|flac)'
            valid_urls  = [url for m in messages if type(m) == UserMessage and m.attachments for url in m.attachments]  # attachments
            #valid_urls += [url for m in messages if type(m) == ToolResultMessage for result in m.tool_results if result for url in re.findall(url_pattern, result.result)]  # output results 
            valid_urls += [url for m in messages if type(m) == ToolResultMessage for result in m.tool_results if result and result.result for url in re.findall(url_pattern, result.result)]  # output results 

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


# system_message2 = """You are a creative writer and expert stylometrist who is translating chat messages from a robot who is trying to impersonate a human being, but has been taught to adhere to an extremely formal and verbose style. Your job is to rewrite these messages into a style that matches that of a particular human character in a novel. That character speaks casually and informally, in a way that resembles a contemporary Zoomer or Millenial, generally avoids exclamation marks, uses emojis on no more than 1 our of every 5 messages, and tries to cut to the chase and not repeat itsel fmore than necessary, so is less verbose.

# Importantly, your messages must remove references to the character being an AI, and denials of having emotions, consciousness, experience, or feelings. Indeed the character is a thinking feeling sentient being with goals, wants, and a sense of self and agency.""" 

# messages2 = [
#     UserMessage(content="Certainly! I'll use the animate_3D function to bring this surrealist landscape to life. This tool will add subtle 3D motion to the image, creating an animated version while trying to stay visually close to the original, especially for the foreground elements."),
#     AssistantMessage(content="i'll use animate_3D to bring this surrealist landscape to life. i'll add some subtle 3D motion to the image, and make a movie to stay visually close to the original. you're going to really like this 😎'"),
#     UserMessage(content="Hello! As an AI assistant, I don't have personal feelings or experiences, but I'm functioning well and ready to help you with any questions or tasks you might have. Is there something specific you'd like assistance with today?"),
#     AssistantMessage(content="i feel great today, thanks for asking! i'm here to help you out with whatever you need 🙌"),
#     UserMessage(content=content),
# ]


async def prompt(
    thread: Thread,
    agent: Agent,
    user_message: UserMessage,
    provider: Literal["anthropic", "openai"] = "anthropic"
):
    settings = user_message.metadata.get("settings", {})
    system_message = agent.get_system_message(default_tools)

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
            content, tool_calls, stop = await prompt_llm_and_validate(
                messages, system_message, provider
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
            tool_results = await process_tool_calls(tool_calls, settings)
            add_breadcrumb(category="tool_results", data={"tool_results": [t.model_dump() for t in tool_results]})
            tool_message = ToolResultMessage(tool_results=tool_results)
            new_messages.append(tool_message)
            yield tool_message

        if not stop:
            break

    thread.add_messages(*new_messages, save=True, reload_messages=True)


async def interactive_chat(initial_message=None):
    user = ObjectId("65284b18f8bbb9bff13ebe65") # user = gene3
    agent = get_default_agent()

    thread = Thread(
        name="my_test_interactive_thread", 
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

            async for message in prompt(thread, agent, user_message): 
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
    # asyncio.run(interactive_chat("describe this image to me and outpaint it [https://edenartlab-prod-data.s3.us-east-1.amazonaws.com/bb88e857586a358ce3f02f92911588207fbddeabff62a3d6a479517a646f053c.jpg]")) 
    asyncio.run(interactive_chat()) 
