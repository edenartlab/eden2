import instructor
from pydantic import BaseModel
from openai import OpenAI
import json
from typing import Literal
from pydantic import Field


from typing import Literal, Optional
from pydantic import BaseModel, Field


from eve.tool import Tool


class RunwayGen3aTurboParameters(BaseModel):
    """Text-guided, realistic image animation with Runway Gen3a. This tool can be used for creating a realistic animation of an image. Specific camera motion"""
    prompt_image: str = Field(..., description="The image to animate")
    prompt_text: str = Field(..., description="The prompt to guide the animation")
    duration: Literal["5", "10"] = Field(
        default="5",
        description="The duration of the video in seconds"
    )
    ratio: Literal["16:9", "9:16"] = Field(
        default="9:16",
        description="The aspect ratio of the video"
    )
    seed: Optional[int] = Field(
        default=None,
        description="Set random seed for reproducibility. If blank, will be set to a random value.",
        ge=0,
        le=2147483647
    )
    watermark: bool = Field(
        default=False,
        description="Add a Runway watermark to the video"
    )


from instructor.function_calls import openai_schema

t1_schema = openai_schema(RunwayGen3aTurboParameters).openai_schema
t2_schema = Tool.load_from_dir("eve/tools/runway").openai_schema()

print(json.dumps(t1_schema, indent=2))
print("------")
print(json.dumps(t2_schema, indent=2))


from eve.base import parse_schema

import yaml
schema = yaml.safe_load(open("eve/tools/runway/api.yaml", "r"))
schema = parse_schema(schema)
                      

print("--------------")
print(RunwayGen3aTurboParameters.model_fields['ratio'])


RunwayGen3aTurboParameters.model_fields['ratio']
Tool.load_from_dir("eve/tools/runway").model.model_fields['ratio']




from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field, conint, confloat

from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field, conint, confloat

class Contact(BaseModel):
    type: Literal["email", "phone", "social_media"] = Field(
        description="The contact method type"
    )
    value: str = Field(description="The contact value", example="john@example.com")

class Address(BaseModel):
    street: str = Field(description="The street address", example="123 Main St")
    city: str = Field(description="The city name", example="Somewhere")
    postal_code: int = Field(
        description="Postal code for the address",
        example=12345,
        # ge=10000, le=99999
    )

class Matrix(BaseModel):
    data: List[List[int]] = Field(
        description="A 2D array of integers (matrix)",
        example=[[1, 2, 3], [4, 5, 6], [7, 8, 9]]
    )

class Widget(BaseModel):
    """This model represents a person with their details like name, age, hobbies, contacts, and address."""
    name: str = Field(
        description="The name of a widget should tell you what it's called",
        example="Wompus"
    )
    type: Literal["thingy", "gadget", "doohickey"] = Field(
        description="This should tell you what kind of a widget you've got",
        default="doohickey"
    )
    age: Optional[int] = Field(
        description="Age of the widget",
        # default="random",
        example=10,
        # ge=-16,
        # le=144
    )
    price: float = Field(
        description="Price of the widget in dollars",
        # default=1.01,
        # ge=0.55,
        # le=2.34
    )
    skills: List[str] = Field(
        description="A list of skills the widget has",
        # default=["reading", "swimming", "cooking"]
    )
    contacts: Optional[List[Contact]] = Field(
        description="A list of contact methods"
    )
    address: Optional[Address] = Field(
        description="The person's address"
    )
    matrix: Optional[Matrix] = Field(
        description="A 2D array of integers (matrix)"
    )



t1_schema = openai_schema(Widget).openai_schema
t2_schema = Tool.load_from_dir("eve/tools/example_tool").openai_schema()

print(json.dumps(t1_schema, indent=2))
print("------")
print(json.dumps(t2_schema, indent=2))



from eve.thread import Thread, UserMessage
from eve.llm import anthropic_prompt, openai_prompt, prompt
from eve.tool import get_tools_from_mongo

system_message = "You are named Abraham. You are an autonomous artist"

user_message = UserMessage(content="make a picture of a cat")

messages = [user_message]

tools = get_tools_from_mongo(db="STAGE")

result = prompt(messages, system_message=system_message, model="claude-3-5-sonnet-20240620", response_model=None, tools=tools)

print(result)

