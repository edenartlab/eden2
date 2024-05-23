import os
import yaml
import random
from enum import Enum
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field, create_model


TYPE_MAPPING = {
    'bool': bool,
    'string': str,
    'int': int,
    'float': float,
    'image': str,
    'video': str,
    'audio': str,
    'zip': str
}

class ParameterType(str, Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    ZIP = "zip"
    BOOL_ARRAY = "bool[]"
    INT_ARRAY = "int[]"
    FLOAT_ARRAY = "float[]"
    STRING_ARRAY = "string[]"
    IMAGE_ARRAY = "image[]"
    VIDEO_ARRAY = "video[]"
    AUDIO_ARRAY = "audio[]"
    ZIP_ARRAY = "zip[]"

FILE_TYPES = [ParameterType.IMAGE, ParameterType.VIDEO, ParameterType.AUDIO, ParameterType.ZIP]
FILE_ARRAY_TYPES = [ParameterType.IMAGE_ARRAY, ParameterType.VIDEO_ARRAY, ParameterType.AUDIO_ARRAY, ParameterType.ZIP_ARRAY]


class ComfyUIInfo(BaseModel):
    node_id: int
    field: str
    subfield: str
    preprocessing: Optional[str] = None


class EndpointParameter(BaseModel):
    name: str
    label: str
    description: str = Field(None, description="Human-readable description of what parameter does")
    tip: str = Field(None, description="Additional tips for a user or LLM on how to use this parameter properly")
    type: ParameterType
    default: Optional[Any] = Field(None, description="Default value")
    minimum: Optional[float] = Field(None, description="Minimum value for int or float type")
    maximum: Optional[float] = Field(None, description="Maximum value for int or float type")
    min_length: Optional[int] = Field(None, description="Minimum length for array type")
    max_length: Optional[int] = Field(None, description="Maximum length for array type")
    choices: Optional[List[Any]] = Field(None, description="Allowed values")
    comfyui: Optional[ComfyUIInfo] = Field(None)


import modal

class Endpoint(BaseModel):
    key: str
    name: str
    description: str = Field(..., description="Human-readable description of what the endpoint does")
    tip: Optional[str] = Field(None, description="Additional tips for a user or LLM on how to get what they want out of this endpoint")
    comfyui_output_node_id: Optional[int] = Field(None, description="ComfyUI node ID of output media")
    parameters: List[EndpointParameter]
    BaseModel: BaseModel = None

    def __init__(self, data, key):
        super().__init__(**data, key=key)
        self.BaseModel = self.create_endpoint_model()

    def create_endpoint_model(self):
        fields = {
            param.name: get_field_type_and_kwargs(param) 
            for param in self.parameters
        }
        EndpointModel = create_model(
            self.key,
            __doc__=f'{self.description}. {self.tip}.',
            **fields
        )
        return EndpointModel

    def summary(self, include_params=True):
        summary = f'"{self.key}" : {self.name} - {self.description}.'
        if self.tip:
            summary += f" {self.tip}."
        if include_params:
            summary += f'\n\n{self.parameters_summary()}'
        return summary

    def parameters_summary(self):
        summary = "Parameters\n---"
        for param in self.parameters:
            summary += f"\n{param.name}: {param.label}. {param.description}."
            if param.tip:
                summary += f" {param.tip}."
        return summary

    # def tool_schema(self):
    #     return {
    #         "type": "function",
    #         "function": openai_schema(self.BaseModel).openai_schema
    #     }
    
    async def execute(self, workflow: str, config: dict):
        #return {"urls": ["https://www.example.com/image1.jpg"]}
        comfyui = f"ComfyUIServer_{workflow}"
        cls = modal.Cls.lookup("comfyui", comfyui)
        workflow_file = f"workflows/{workflow}.json"
        endpoint_file = f"endpoints/{workflow}.yaml"

        result = await cls().run.remote.aio(
            workflow_file,
            endpoint_file,
            config, 
            "client_id"
        )

        return result
        # print(self.tool_schema())


def get_field_type_and_kwargs(param: EndpointParameter) -> (Type, Dict[str, Any]):
    field_kwargs = {
        'description': param.description,
    }

    is_list = param.type.endswith('[]')
    field_type = TYPE_MAPPING[param.type.rstrip('[]')]
    
    if is_list:
        field_type = List[field_type]
        if param.min_length is not None:
            field_kwargs['min_items'] = param.min_length
        if param.max_length is not None:
            field_kwargs['max_items'] = param.max_length

    default = param.default
    if default == 'random':
        assert not param.minimum or not param.maximum, \
            "If default is random, minimum and maximum must be specified"
        field_kwargs['default_factory'] = lambda min_val=param.minimum, max_val=param.maximum: random.randint(min_val, max_val)
    elif default:
        field_kwargs['default_factory'] = lambda: default
    #elif not default and not param.required: 
        #field_kwargs['default_factory'] = lambda: list() if is_list else None
        #print("ok")

    if param.minimum is not None:
        field_kwargs['ge'] = param.minimum
    if param.maximum is not None:
        field_kwargs['le'] = param.maximum
    if param.choices is not None:
        field_kwargs['choices'] = param.choices

    #if not param.required:
    field_type = Optional[field_type]

    return (field_type, Field(**field_kwargs))
            

endpoint_names = sorted([
    f.replace(".yaml", "") 
    for f in os.listdir("endpoints") if f.endswith(".yaml")
])

tools = {}
endpoint_summary = ""

for endpoint_name in endpoint_names:
    with open(f"endpoints/{endpoint_name}.yaml", "r") as f:
        data = yaml.safe_load(f)
    tool = Endpoint(data, key=endpoint_name)    
    tools[endpoint_name] = tool
    endpoint_summary += f"{tool.summary(include_params=False)}\n"

snapshots = [
    "txt2img", 
    "txt2vid_lcm", 
    "img2vid", 
    "vid2vid",
    "style_mixing"
]
