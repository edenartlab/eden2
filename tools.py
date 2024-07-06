import os
import yaml
import json
import random
import modal
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Literal
from pydantic import BaseModel, Field, ValidationError, create_model
from pydantic.json_schema import SkipJsonSchema
from instructor.function_calls import openai_schema

from models import Task

DEFAULT_APP_NAME = "comfyui-dev"


TYPE_MAPPING = {
    "bool": bool,
    "string": str,
    "int": int,
    "float": float,
    "image": str,
    "video": str,
    "audio": str,
    "zip": str,
    "lora": str
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
    LORA = "lora"
    BOOL_ARRAY = "bool[]"
    INT_ARRAY = "int[]"
    FLOAT_ARRAY = "float[]"
    STRING_ARRAY = "string[]"
    IMAGE_ARRAY = "image[]"
    VIDEO_ARRAY = "video[]"
    AUDIO_ARRAY = "audio[]"
    ZIP_ARRAY = "zip[]"
    LORA_ARRAY = "lora[]"

FILE_TYPES = [ParameterType.IMAGE, ParameterType.VIDEO, ParameterType.AUDIO]

FILE_ARRAY_TYPES = [ParameterType.IMAGE_ARRAY, ParameterType.VIDEO_ARRAY, ParameterType.AUDIO_ARRAY]


class ToolParameter(BaseModel):
    name: str
    label: str
    description: str = Field(None, description="Human-readable description of what parameter does")
    tip: str = Field(None, description="Additional tips for a user or LLM on how to use this parameter properly")
    type: ParameterType
    required: bool = Field(False, description="Indicates if the field is mandatory")
    default: Optional[Any] = Field(None, description="Default value")
    minimum: Optional[float] = Field(None, description="Minimum value for int or float type")
    maximum: Optional[float] = Field(None, description="Maximum value for int or float type")
    min_length: Optional[int] = Field(None, description="Minimum length for array type")
    max_length: Optional[int] = Field(None, description="Maximum length for array type")
    choices: Optional[List[Any]] = Field(None, description="Allowed values")

class Tool(BaseModel):
    key: str
    name: str
    description: str = Field(..., description="Human-readable description of what the tool does")
    tip: Optional[str] = Field(None, description="Additional tips for a user or LLM on how to get what they want out of this tool")
    gpu: SkipJsonSchema[Optional[str]] = Field("A100", description="Which GPU to use for this tool", exclude=True)
    parameters: List[ToolParameter]

    def __init__(self, data, key):
        super().__init__(**data, key=key)

    def get_base_model(self, **kwargs):
        base_model = create_tool_base_model(self)
        return base_model(**kwargs)

    def summary(self, include_params=True):
        summary = f'"{self.key}" :: {self.name} - {self.description}.'
        if self.tip:
            summary += f" {self.tip}."
        if include_params:
            summary += f'\n\n{self.parameters_summary()}'
        return summary

    def parameters_summary(self):
        summary = "Parameters\n---"
        for param in self.parameters:
            summary += f"\n{param.name}: {param.label}, {param.description}."
            if param.tip:
                summary += f" {param.tip}."
            requirements = ["Type: " + param.type.name]
            if not param.default:
                requirements.append("Field required")
            if param.choices:
                requirements.append("Allowed choices: " + ", ".join(param.choices))
            if param.minimum or param.maximum:
                requirements.append(f"Range: {param.minimum} to {param.maximum}")
            if param.min_length or param.max_length:
                requirements.append(f"Allowed length: {param.min_length} to {param.max_length}")
            requirements_str = "; ".join(requirements)
            summary += f" ({requirements_str})"
        return summary

    def tool_schema(self):
        tool_model = create_tool_base_model(self)
        return {
            "type": "function",
            "function": openai_schema(tool_model).openai_schema
            # "function": openai_schema(tool_model).anthropic_schema
        }

    def prepare_args(self, user_args, save_files=False):
        args = {}

        for param in self.parameters:
            key = param.name
            value = None

            if param.default is not None:
                value = param.default

            if user_args.get(key):
                value = user_args[key]

            if value == "random":
                value = random.randint(param.minimum, param.maximum)

            args[key] = value

        unrecognized_args = set(user_args.keys()) - {param.name for param in self.parameters}
        if unrecognized_args:
            raise ValueError(f"Unrecognized arguments provided: {', '.join(unrecognized_args)}")

        try:
            create_tool_base_model(self)(**args)  # validate args
        except ValidationError as e:
            error_str = get_human_readable_error(e.errors())
            raise ValueError(error_str)

        return args

    def test_args(self):
        args = json.loads(open(f"../workflows/{self.key}/test.json", "r").read())
        return self.prepare_args(args)


def create_tool_base_model(tool: Tool):
    fields = {
        param.name: get_field_type_and_kwargs(param) 
        for param in tool.parameters
    }
    ToolBaseModel = create_model(tool.key, **fields)
    ToolBaseModel.__doc__ = f'{tool.description}. {tool.tip}.'
    return ToolBaseModel


def get_field_type_and_kwargs(param: ToolParameter) -> (Type, Dict[str, Any]):
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
    elif default is not None:
        field_kwargs['default_factory'] = lambda: default
    else:
        if param.required:
            field_kwargs['default'] = ...
        else:
            field_type = Optional[field_type]
            field_kwargs['default'] = None

    if param.minimum is not None:
        field_kwargs['ge'] = param.minimum
    if param.maximum is not None:
        field_kwargs['le'] = param.maximum
    if param.choices is not None:
        field_kwargs['choices'] = param.choices
        field_type = Literal[*param.choices]
    
    return (field_type, Field(**field_kwargs))
            

def load_tool(tool_path: str, name: str = None) -> Tool:    
    api_path = f"{tool_path}/api.yaml"    
    if not os.path.exists(api_path):
        raise ValueError(f"Tool {name} not found at {api_path}")
    if name is None:
        name = os.path.relpath(tool_path, start=os.path.dirname(tool_path))
    data = yaml.safe_load(open(api_path, "r"))
    if data['handler'] == 'comfyui':
        tool = ComfyUITool(data, key=name)
    elif data['handler'] == 'replicate':
        tool = ReplicateTool(data, key=name)
    else:
        tool = Tool(data, key=name)
    return tool


def get_tools(tools_folder: str, exclude: List[str] = []):
    required_files = {'api.yaml', 'test.json'}
    tools = {}
    for root, _, files in os.walk(tools_folder):
        name = os.path.relpath(root, start=tools_folder)
        if "." in name or name in exclude or not required_files <= set(files):
            continue
        tools[name] = load_tool(os.path.join(tools_folder, name), name)
    return tools


def get_tools_summary(tools: List[Tool]):    
    tools_summary = ""
    for tool in tools.values():
        tools_summary += f"{tool.summary(include_params=False)}\n"
    return tools_summary


def get_human_readable_error(error_list):
    print("error_list", error_list)
    errors = []
    for error in error_list:
        field = error['loc'][0]
        error_type = error['type']
        input_value = error['input']
        if error_type == 'string_type':
            errors.append(f"{field} is missing")
        elif error_type == 'literal_error':
            expected_values = error['ctx']['expected']
            errors.append(f"{field} must be one of {expected_values}")
        elif error_type == 'less_than_equal':
            max_value = error['ctx']['le']
            errors.append(f"{field} must be ≤ {max_value}")
        elif error_type == 'greater_than_equal':
            min_value = error['ctx']['ge']
            errors.append(f"{field} must be ≥ {min_value}")
        elif error_type == 'value_error.any_str.min_length':
            min_length = error['ctx']['limit_value']
            errors.append(f"{field} must have at least {min_length} characters")
        elif error_type == 'value_error.any_str.max_length':
            max_length = error['ctx']['limit_value']
            errors.append(f"{field} must have at most {max_length} characters")
        elif error_type == 'enum':
            choices = ", ".join(error['ctx']['enum_values'])
            errors.append(f"{field} must be one of [{choices}]")
        elif error_type == 'type_error.integer':
            errors.append(f"{field} must be an integer")
        elif error_type == 'type_error.float':
            errors.append(f"{field} must be a float")
        elif error_type == 'type_error.boolean':
            errors.append(f"{field} must be a boolean")
        elif error_type == 'type_error.list':
            errors.append(f"{field} must be a list")
        elif error_type == 'type_error.none.not_allowed':
            errors.append(f"{field} cannot be None")
    error_str = ", ".join(errors)
    error_str = f"Invalid args: {error_str}"
    return error_str


class ComfyUIInfo(BaseModel):
    node_id: int
    field: str
    subfield: str
    preprocessing: Optional[str] = None


class ComfyUIParameter(ToolParameter):
    comfyui: Optional[ComfyUIInfo] = Field(None)


class ComfyUITool(Tool):
    parameters: List[ComfyUIParameter]
    comfyui_output_node_id: Optional[int] = Field(None, description="ComfyUI node ID of output media")

    def submit(self, task: Task, app_name=DEFAULT_APP_NAME):
        task.args = self.prepare_args(task.args)
        cls = modal.Cls.lookup(app_name, task.workflow)
        job = cls().api.spawn(task.to_mongo())
        return job.object_id

    async def run(self, workflow: str, args: Dict, app_name=DEFAULT_APP_NAME):
        args = self.prepare_args(args)
        cls = modal.Cls.lookup(app_name, workflow)
        result = await cls().execute.remote.aio(args)
        return result


class ReplicateTool(Tool):
    model: str

    # def submit(self, task: Task):
    #     task.args = self.prepare_args(task.args)
        
    async def run(self, args: Dict):
        import replicate
        args = self.prepare_args(args)
        output = await replicate.async_run(self.model, input=args)
        result = list(output)
        return result
