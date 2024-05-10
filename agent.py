import openai
import instructor
from typing import Iterable, Literal, Union
from pydantic import BaseModel

from config_utils import *


endpoint_names = ["txt2img", "txt2vid_lcm"]

endpoints = {}
for endpoint in endpoint_names:
    with open(f"{endpoint}.yaml", "r") as f:
        data = yaml.safe_load(f)
        endpoints[endpoint] = Endpoint(data)





print(endpoints["txt2vid_lcm"].summary())





query = "can you make a portrait-orientation video of a fancy cat in some kind of 19th century style, and use the image myImage.jpg as a starting point? Make sure it is *not* blurry! use model SDXL model please if you can."




endpoints_summary = "\n".join([endpoint.summary(include_params=False) for endpoint in endpoints.values()])

system_message = f'You are an assistant that knows how to use Eden. You have the following tools available to you.\n\n{endpoints_summary}.\n\nA user will give you a prompt and you need to select exactly one of the tools to use to serve that prompt.'

client = instructor.from_openai(openai.OpenAI(), mode=instructor.Mode.TOOLS)

model = "gpt-3.5-turbo" #"gpt-4-turbo-preview",

workflow = client.chat.completions.create(
    model=model, 
    messages=[
        {
            "role": "system", 
            "content": system_message
        },
        {
            "role": "user",
            "content": query
        },
    ],
    #response_model=Union[Weather, GoogleSearch],
    response_model=Literal[*endpoints],
)



endpoint = endpoints[workflow]
EndpointModel = endpoint.BaseModel


print("GOT WORKFLOW", workflow)
print(endpoint)

print("=====")


print(EndpointModel)


output_type = "video"



endpoint_instructions = endpoints["txt2vid_lcm"].summary(include_params=True)

fields_description = "\n".join(f"{name}: {value.description}" for name, value in EndpointModel.__fields__.items())


system_message = f'You are an assistant that knows how to use Eden. You receive a prompt from a user who would like to make {output_type}s using the tool "{endpoint}: Here is a description of {endpoint}".\n\n{endpoint_instructions}\n\n{fields_description}'

print(system_message)


config = client.chat.completions.create(
    model="gpt-4-turbo-preview",
    messages=[
        {"role": "system", "content": system_message},
        {
            "role": "user",
            "content": "can you make a portrait-orientation video of a fancy cat in some kind of 19th century style, and use the image myImage.jpg as a starting point? Make sure it is *not* blurry! use model SDXL model please if you can."
        },
    ],
    response_model=EndpointModel,
)

# Parallel tool calling is also an option but you must set `response_model` to be `Iterable[Union[...]]` types since we expect an array of results. Check out [Parallel Tool Calling](./parallel.md) for more information.


config = EndpointModel(**{k: v for k, v in config.dict().items() if v})

print(config)

# raise Exception("stop")
# for fc in function_calls:
#     print(fc)
