from pydantic import BaseModel, create_model, Field, validator, constr, conint, confloat
from typing import Any, Dict, List, Optional, Union, Type
from enum import Enum
import yaml
import json
import random


TYPE_MAPPING = {
    'boolean': bool,
    'string': str,
    'int': int,
    'float': float,
    'image': str,
    'video': str,
    'audio': str,
    'zip': str
}


class ParameterType(str, Enum):
    BOOL = "boolean"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    ZIP = "zip"
    BOOL_ARRAY = "boolean[]"
    INT_ARRAY = "int[]"
    FLOAT_ARRAY = "float[]"
    STRING_ARRAY = "string[]"
    IMAGE_ARRAY = "image[]"
    VIDEO_ARRAY = "video[]"
    AUDIO_ARRAY = "audio[]"
    ZIP_ARRAY = "zip[]"


class ComfyUIInfo(BaseModel):
    node_id: int
    field: str
    subfield: str
    preprocessing: Optional[str] = None


class EndpointParameter(BaseModel):
    """
    Endpoint parameter class model
    """

    type: ParameterType = Field(..., description="Parameter type")
    name: str = Field(..., description="Parameter name")
    label: str = Field(..., description="Human-readable parameter name")
    description: str = Field(..., description="Short description of parameter")
    tip: Optional[str] = Field(None, description="Tips for user or LLM to use this parameter")
    # required: Optional[bool] = Field(False, description="Parameter required as input")
    default: Optional[Any] = Field(None, description="Default value")
    minimum: Optional[int] = Field(None, description="Minimum value")
    maximum: Optional[int] = Field(None, description="Maximum value")
    min_length: Optional[int] = Field(None, description="Minimum length of array")
    max_length: Optional[int] = Field(None, description="Maximum length of array")
    choices: Optional[List[Any]] = Field(None, description="Allowed values")
    comfyui: Optional[ComfyUIInfo] = Field(None, description="ComfyUI info")


class EndpointBaseModel(BaseModel):
    def __str__(self):
        return json.dumps(self.dict(), indent=4)


class Endpoint(BaseModel):
    """
    Endpoint class model
    """

    name: str = Field(..., description="Endpoint name")
    description: str = Field(..., description="Endpoint description")
    tip: Optional[str] = Field(None, description="A tip to help the user understand what this endpoint does")
    comfyui_output_node_id: Optional[int] = Field(None, description="ComfyUI node ID of output media")
    parameters: List[EndpointParameter]
    BaseModel: BaseModel = None

    def __init__(self, data):
        super().__init__(**data)
        self.BaseModel = self.create_endpoint_model()

    def create_endpoint_model(self):
        fields = {
            param.name: get_field_type_and_kwargs(param) 
            for param in self.parameters
        }
        EndpointModel = create_model(
            f'{endpoint}_Model',
            __base__=EndpointBaseModel, 
            **fields
        )
        return EndpointModel

    def summary(self, include_params=True):
        summary = f"{self.name}: {self.description}."
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


def get_field_type_and_kwargs(param: EndpointParameter) -> (Type, Dict[str, Any]):
    """
    Helper method to convert yaml description of endpoint parameter to pydantic field
    """

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
            









endpoint_names = ["txt2img", "txt2vid_lcm"]

endpoints = {}
for endpoint in endpoint_names:
    with open(f"{endpoint}.yaml", "r") as f:
        data = yaml.safe_load(f)
        endpoints[endpoint] = Endpoint(data)

        # Instantiate the model
        EndpointModel = endpoints[endpoint].BaseModel
        try:
            instance = EndpointModel(
                prompt="Sample prompt", 
            )
            print(instance)
        except Exception as e:
            print(f"An error occurred: {e}")
