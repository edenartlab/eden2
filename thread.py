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

from agent import Agent, get_default_agent
from tool import Tool, get_tools
from mongo import MongoBaseModel, threads

workflows = get_tools("../workflows", exclude=["xhibit/vton", "xhibit/remix"])
extra_tools = get_tools("tools")
default_tools = workflows | extra_tools

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    createdAt: datetime = Field(default_factory=datetime.utcnow, exclude=True)
    
    def to_mongo(self, **kwargs):
        data = self.model_dump()
        data["createdAt"] = self.createdAt
        return data
    
## class thinkmessage
## save it to db, don't send it to openai, show users but not run as part of anything else

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
    name: Optional[str] = Field(None, description="The name of the tool")
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
            functions = [f"{tc.function.name}: {tc.function.arguments}" for tc in self.tool_calls]
            tool_call_str = "\n".join(functions)            
        else:
            tool_call_str = ""
        return f"\033[93m\033[1mAI\t\033[22m{content_str}{tool_call_str}\033[0m"

class GhostMessage(ChatMessage):
    role: Literal["ghost"] = "ghost"
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = Field({}, description="Preset settings, metadata, or context information")



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
    name: str
    user: ObjectId
    messages: List[Union[UserMessage, AssistantMessage, SystemMessage, ToolMessage]] = []
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

    def get_chat_messages(self, system_message: str = None):
        system_message = SystemMessage(content=system_message)
        messages = [system_message, *self.messages]
        return [m.chat_message() for m in messages]

    def add_message(self, *messages: ChatMessage):
        self.messages.extend(messages)
        self.save()
    
    async def prompt(
        self, 
        agent: Agent,
        user_message: UserMessage,
    ):
        # local for prints
        verbose = True
        self.add_message(user_message)  
        system_message = agent.get_system_message(self.tools)
        #if verbose: print(f'Line 186: System message: {system_message}')

        response = await prompt(
            self.get_chat_messages(system_message=system_message),
            tools=[t.tool_schema() for t in self.tools.values()]
        )
        #### original msg
        #### output looks like this:
        '''
        Line 193: AI response: ChatCompletionMessage(content=None, role='assistant', function_call=None, tool_calls=[ChatCompletionMessageToolCall(id='call_rBQ3doIsGHMT0LIU0FgO3ltw', function=Function(arguments='{"prompt":"A man standing in a field of ghost orchids at twilight, creating a dark and surreal atmosphere. The scene is bathed in soft, eerie moonlight, casting long shadows and giving the orchids an ethereal glow. The man, dressed in a simple, dark outfit, appears contemplative as he looks at the delicate flowers.","negative_prompt":"bright, sunny, cheerful","width":1024,"height":768,"seed":null,"lora":null,"lora_strength":0,"denoise":0.3}', name='txt2img2'), type='function')])
        '''

        # message = response.choices[0].message
        # if verbose: print(f'Line 193: AI response: {message}') #this is the prompt + the function parameters and the function name

        ### reasoning version
        # reasoning + action loop for determining the tool to use
        tool_choice_prompt = """
        Thought: I need to determine which tool to use for the user's request.
        Action: Choose a tool from the available tools.
        Action Input: "Which tool should I use for this request?"
        """
        tool_response = await prompt(
            self.get_chat_messages(system_message=system_message + tool_choice_prompt),
            tools=[t.tool_schema() for t in self.tools.values()]
        )
        print(tool_response)
        chosen_tool = tool_response.choices[0].message.tool_calls[0].function.name
        if verbose: print(f'Line 193: Chosen tool: {chosen_tool}')

        # reasoning + action loop for generating the prompt
        prompt_choice_prompt = f"""
        Thought: I need to generate a prompt given the user request ({response}) for the chosen tool ({chosen_tool}).
        Action: Generate a prompt based on the user's request.
        Action Input: "What should the prompt be?"
        """
        print(f"Prompt going into reasoning loop: {prompt_choice_prompt}")
        prompt_response = await prompt(
            self.get_chat_messages(system_message=prompt_choice_prompt),
            tools=[t.tool_schema() for t in self.tools.values()]
        )
        generated_prompt = prompt_response.choices[0].message.content
        if verbose: print(f'Line 197: Generated prompt: {generated_prompt}')

        # reasoning + action loop for generating the negative prompt
        negative_prompt_choice_prompt = f"""
        Thought: I need to generate a negative prompt given the user request ({response}) for the chosen tool ({chosen_tool}).
        Action: Generate a negative prompt based on the user's request.
        Action Input: "What should the negative prompt be?"
        """
        negative_prompt_response = await prompt(
            self.get_chat_messages(system_message=negative_prompt_choice_prompt),
            tools=[t.tool_schema() for t in self.tools.values()]
        )
        generated_negative_prompt = negative_prompt_response.choices[0].message.content
        if verbose: print(f'Line 201: Generated negative prompt: {generated_negative_prompt}')

        # reasoning + action loop for generating the parameters
        parameters_choice_prompt = f"""
        Thought: I need to generate parameters given the user request ({response}) for the chosen tool ({chosen_tool}).
        Action: Generate parameters based on the user's request and the given tool.
        Action Input: "What should the parameters be?"
        """
        parameters_response = await prompt(
            self.get_chat_messages(parameters_choice_prompt),
            tools=[t.tool_schema() for t in self.tools.values()]
        )
        generated_parameters = json.loads(parameters_response.choices[0].message.content)
        if verbose: print(f'Line 205: Generated parameters: {generated_parameters}')

        # combine the generated information into the final format
        final_message = {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call_rBQ3doIsGHMT0LIU0FgO3ltw",
                    "function": {
                        "name": chosen_tool,
                        "arguments": json.dumps({
                            "prompt": generated_prompt,
                            "negative_prompt": generated_negative_prompt,
                            **generated_parameters
                        })
                    },
                    "type": "function"
                }
            ]
        }
        if verbose: print(f'Line 213: Final message: {final_message}')
        message = final_message #temporary


        ## adding a trycatch breakout for fixing
        try: tool_calls = message.tool_calls
        except: 
            print(f'reasoning loop format was not correct. output: \n {message}')
            exit()

        if not tool_calls:
            assistant_message = AssistantMessage(**message.model_dump())
            self.add_message(assistant_message)
            if verbose: print(f'Line 199: No tool calls, assistant message: {assistant_message}')
            yield assistant_message
            return  # no tool calls, we're done

        if verbose: print(f'Line 203: Tool calls: {tool_calls[0]}')
        args = json.loads(tool_calls[0].function.arguments)
        tool_name = tool_calls[0].function.name
        tool = self.tools.get(tool_name)

        if tool is None:
            raise Exception(f"Tool {tool_name} not found")

        try:
            extra_args = user_message.metadata.get('settings', {})
            args = {k: v for k, v in args.items() if v is not None}
            args.update(extra_args)
            if verbose: print(f'Line 215: Args: {args}')
            updated_args = tool.get_base_model(**args).model_dump()
            if verbose: print(f'Line 217: Updated args: {updated_args}')

        except ValidationError as err:
            assistant_message = AssistantMessage(**message.model_dump())
            yield assistant_message

            error_details = "\n".join([f" - {e['loc'][0]}: {e['msg']}" for e in err.errors()])
            error_message = f"{tool_name}: {args} failed with errors:\n{error_details}"
            if verbose: print(f'Line 225: Error message: {error_message}')
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
        
        # todo: actually handle multiple tool calls
        if len(message.tool_calls) > 1:
            if verbose: print(f'Line 242: Multiple tool calls found, only using the first one: {message.tool_calls}')
            message.tool_calls = [message.tool_calls[0]]
        
        message.tool_calls[0].function.arguments = json.dumps(updated_args)
        assistant_message = AssistantMessage(**message.model_dump())
        yield assistant_message
        
        result = await tool.async_run(
            args=updated_args
        )
        if verbose: print(f'Line 252: Tool result: {result}')

        if isinstance(result, list):
            result = ", ".join(result)

        tool_message = ToolMessage(
            name=tool_calls[0].function.name,
            tool_call_id=tool_calls[0].id,
            content=result
        )

        self.add_message(assistant_message, tool_message)
        if verbose: print(f'Line 264: Final tool message: {tool_message}')
        yield tool_message

## update logic here
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
    print('starting')
    user = ObjectId("65284b18f8bbb9bff13ebe65") # user = gene3
    print('getting eve')
    agent = get_default_agent() # eve
    print("got eve")
    tools = get_tools("../workflows", exclude=["xhibit/remix", "xhibit/vton", "blend"])
    print("got tools")
    print('b4 thread')
    thread = Thread(
        name="my_test_thread", 
        user=user,
        tools=tools
    )
    print('after thread')
    
    while True:
        try:
            message_input = input("\033[92m\033[1mUser:\t")
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
    attachments_match = re.search(attachments_pattern, message)
    metadata = json.loads(metadata_match.group(0)) if metadata_match else {}
    attachments = json.loads(attachments_match.group(0)) if attachments_match else []
    clean_message = re.sub(metadata_pattern, '', message)
    clean_message = re.sub(attachments_pattern, '', clean_message).strip()
    return clean_message, metadata, attachments

if __name__ == "__main__":
    import asyncio
    asyncio.run(interactive_chat())
