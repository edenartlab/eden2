import re
import json
import os
import uuid
import openai
import instructor
from typing import Iterable, Literal, Union
from pydantic import BaseModel, HttpUrl
from typing import Literal, Optional, Dict, Any, List

from config_utils import *

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class FunctionCall(BaseModel):
    name: str
    args: Dict[str, Any]

    def __repr__(self):
        return {
            "name": self.name,
            "arguments": self.args,
        }
    
    def chat_message(self):
        return {
            "name": self.name,
            "arguments": json.dumps(self.args),
        }


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: Optional[str] = None

    def chat_message(self):
        return {
            "role": self.role,
            "content": self.content,
        }

    def __repr__(self):
        return json.dumps(self.chat_message(), indent=4)


class SystemMessage(ChatMessage):
    role: Literal["system"] = "system"
    content: str = "You are an assistant"

    def __str__(self):
        return f"\033[91m\033[1m{self.role.capitalize()}\t\033[22m{self.content}\033[0m"


class UserMessage(ChatMessage):
    role: Literal["user"] = "user"
    settings: Dict[str, Any] = {}
    attachments: Optional[List[HttpUrl]] = []

    def chat_message(self):
        return {
            "role": self.role,
            "content": json.dumps({
                "message": self.content,
                "settings": self.settings,
                "attachments": [str(url) for url in self.attachments],
            })
        }

    def __str__(self):
        attachments = [str(url) for url in self.attachments]
        attachments_str = ", ".join(attachments)
        attachments_str = f"\n\tAttachments: [{attachments_str}]" if attachments_str else ""
        settings_str = f"\n\tSettings: {json.dumps(self.settings)}" if self.settings else ""
        return f"\033[92m\033[1mUser\t\033[22m{self.content}{settings_str}{attachments_str}\033[0m"


class AssistantMessage(ChatMessage):
    role: Literal["assistant"] = "assistant"
    function_call: Optional[FunctionCall] = None

    def chat_message(self):
        if self.function_call:
            return {
                "role": self.role,
                "function_call": self.function_call.chat_message(),
            }
        else:
            return super().chat_message()

    def __str__(self):
        content_str = f"{self.content}\n" if self.content else ""
        if self.function_call:
            function_call_str = f"Function Call: {json.dumps(self.function_call.__repr__())}"
        else:
            function_call_str = ""
        return f"\033[93m\033[1mAI\t\033[22m{content_str}{function_call_str}\033[0m"


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    messages : List[ChatMessage] = []
    context: Optional[Dict[str, str]] = {}

    def __init__(self, system_message: str = None):
        super().__init__()
        if system_message:
            self.add_message(SystemMessage(content=system_message))

    def chat_messages(self):
        return [m.chat_message() for m in self.messages]

    def add_message(self, message: ChatMessage):
        self.messages.append(message)

    def prompt(self, user_message: UserMessage):
        self.add_message(user_message)
        workflow = get_model(self)
        assistant_message = AssistantMessage(
            function_call=FunctionCall(
                name=type(workflow).__name__, 
                args=workflow.dict()
            )
        )
        self.add_message(assistant_message)
        return assistant_message





endpoint_names = ["txt2img", "img2vid"]
endpoints = {}
base_models = []
for endpoint in endpoint_names:
    with open(f"endpoints/{endpoint}.yaml", "r") as f:
        data = yaml.safe_load(f)
        endpoints[endpoint] = Endpoint(data)
        base_models.append(endpoints[endpoint].BaseModel)


class ChatModel(BaseModel):
    """
    Simple chat message sent without a tool call 
    """
    content: str

#BaseModels = Union[ChatModel, *base_models]
BaseModels = Union[*base_models]
print(BaseModels)



def get_model(session: Session) -> BaseModels:
    client = instructor.from_openai(openai.OpenAI(), mode=instructor.Mode.TOOLS)
    model = "gpt-3.5-turbo"  # "gpt-4-turbo-preview",
    model = "gpt-4-1106-preview"

    endpoints_summary = "\n".join([endpoint.summary(include_params=False) for endpoint in endpoints.values()])
    system_message = f'You are an assistant that knows how to use Eden. You have the following tools available to you.\n\n{endpoints_summary}.\n\nA user will give you a prompt and you need to select exactly one of the tools to use to serve that prompt. '


    return client.chat.completions.create(
        model=model, 
        messages=session.chat_messages(),
        response_model=BaseModels,
        # response_model=Literal[*endpoints],
    )

def preprocess_message(message):
    settings_pattern = r'\{.*?\}'
    attachments_pattern = r'\[.*?\]'
    settings_match = re.search(settings_pattern, message)
    attachments_match = re.search(attachments_pattern, message)
    settings = json.loads(settings_match.group(0)) if settings_match else {}
    attachments = json.loads(attachments_match.group(0)) if attachments_match else []
    clean_message = re.sub(settings_pattern, '', message)
    clean_message = re.sub(attachments_pattern, '', clean_message).strip()
    return clean_message, settings, attachments



# def main2():
#     session = Session("You are an assistant. Pay attention to the settings in your response.")
#     user_message = UserMessage(
#         content="starting from this image, make a picture on top of it of an astronaut",
#         settings={"style": "starry night style"}, 
#         attachments=["https://edenartlab-lfs.s3.amazonaws.com/comfyui/models2/checkpoints/photonLCM_v10.safetensors"]
#     )
#     assistant_message = session.prompt(user_message)
#     print(user_message)
#     print(assistant_message)



def interactive_chat():
    session = Session("You are an assistant. Pay attention to the settings in your response.")
    while True:
        try:
            message_input = input("\033[92m\033[1mUser: \t")
            if message_input.lower() == 'escape':
                break
            content, settings, attachments = preprocess_message(message_input)
            user_message = UserMessage(
                content=content,
                settings=settings,
                attachments=attachments
            )  
            print("\033[A\033[K", end='')  # Clears the input line
            print(user_message)
            assistant_message = session.prompt(user_message)
            print(assistant_message)
            
        except KeyboardInterrupt:
            break

        
if __name__ == "__main__":
    interactive_chat()









# print(assistant_message)


#print(session.messages)
# for message in messages:
#     print(json.dumps(message.chat_message(), indent=4))



# messages2 = [
#     {
#         "role": "system", 
#         "content": system_message
#     },
#     {
#         "role": "assistant",
#         "function_call": {
#             "name": "Text_to_Image_Model",
#             "arguments": json.dumps({
#                 "prompt": "A fancy cat in some kind of 19th century style",
#                 "negative_prompt": "blurry",
#                 "width": 1280,
#                 "height": 720,
#                 "seed": 123456789
#             })
#         }
#     }
# ]


# print(session.messages)


#print(assistant_message.chat_message())
#print(messages)

#print([m.chat_message() for m in messages])






# msg1 = UserChatMessage(content="this is a dog")
# msg2 = AssistantChatMessage(content="this is a dog")





# messages.append(msg1)
# messages.append(msg2)

# print(messages)

# print([m.dict() for m in messages])

# messages.append({
#     "role": "user",
#     "content": query1,
# })



# query1 = "can you make a portrait-orientation video of a fancy cat in some kind of 19th century style, and use the image myImage.jpg as a starting point? Make sure it is *not* blurry! use model SDXL model please if you can."

# query2 = "convert this image of a dog into a video, its called myDog.jpg"

# query3 = "do the same thing as the first image, but make it a pig, and go the opposite orientation. same seed"

# endpoints_summary = "\n".join([endpoint.summary(include_params=False) for endpoint in endpoints.values()])

# system_message = f'You are an assistant that knows how to use Eden. You have the following tools available to you.\n\n{endpoints_summary}.\n\nA user will give you a prompt and you need to select exactly one of the tools to use to serve that prompt. '

# client = instructor.from_openai(openai.OpenAI(), mode=instructor.Mode.TOOLS)

# model = "gpt-3.5-turbo" #"gpt-4-turbo-preview",
# import json

# b1 = endpoints["txt2img"].BaseModel
# b2 = endpoints["img2vid"].BaseModel


# messages = messages=[
#     {
#         "role": "system", 
#         "content": system_message
#     },
#     {
#         "role": "user",
#         "content": query1,
#     },
#     {
#         "role": "assistant",
#         "content": "this is another tool ",
#         # "function_call": {
#         #     "name": "Text_to_Image_Model",
#         #     "arguments": json.dumps({
#         #         "prompt": "A fancy cat in some kind of 19th century style",
#         #         "negative_prompt": "blurry",
#         #         "width": 1280,
#         #         "height": 720,
#         #         "seed": 123456789
#         #     })
#         # }
#         "tool_call": {
#             "tool": "Text_to_Image_Model",
#             "arguments": {
#                 "prompt": "A fancy cat in some kind of 19th century style",
#                 "negative_prompt": "blurry",
#                 "width": 1280,
#                 "height": 720,
#                 "seed": 123456789
#             }
#         }
#     },
#     {
#         "role": "assistant",
#         "content": '{"output": "67dcn367f.jpg"}'
#     },
#     {
#         "role": "user",
#         "content": query2,
#     },
#     {
#         "role": "assistant",
#         "function_call": {
#             "name": "Text_to_Video_Model",
#             "arguments": json.dumps({
#                 "image": "myDog.jpg"
#             })
#         }
#     },
#     {
#         "role": "assistant",
#         "content": '{"output": "f4smkG258d.mp4"}'
#     },
#     {
#         "role": "user",
#         "content": "take the first image you made, and turn it into a video",
#     },

# ]

# workflow = client.chat.completions.create(
#     model=model, 
#     messages=messages,
#     response_model=Union[b1, b2],
#     # response_model=Literal[*endpoints],
# )

# print(workflow)
# print(workflow.model_json_schema())

# """
# {
#             "role": "assistant",
#             "function_call": {
#                 "name": "attachments",
#                 "arguments": '{"a":133,"b":539,"result":89509}',
#             },
#         }
# """

# print("GOT THE WORKFLOW!")
# print(workflow)

# # get name of the function
# print(type(workflow).__name__)


#endpoint = endpoints[workflow]
#EndpointModel = endpoint.BaseModel

