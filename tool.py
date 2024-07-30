import os
import yaml
import json
import random
import asyncio
import modal
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Literal
from pydantic import BaseModel, Field, ValidationError, create_model
from pydantic.json_schema import SkipJsonSchema
from instructor.function_calls import openai_schema

from utils import mock_image
from models import Task

env = os.getenv("ENV", "STAGE")
DEFAULT_APP_NAME = "comfyui" if env == "PROD" else "comfyui-dev"


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

ARRAY_TYPES = [ParameterType.BOOL_ARRAY, ParameterType.INT_ARRAY, ParameterType.FLOAT_ARRAY, ParameterType.STRING_ARRAY, ParameterType.IMAGE_ARRAY, ParameterType.VIDEO_ARRAY, ParameterType.AUDIO_ARRAY, ParameterType.LORA_ARRAY, ParameterType.ZIP_ARRAY]


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
    output_type: ParameterType = Field(None, description="Output type from the tool")
    gpu: SkipJsonSchema[Optional[str]] = Field("A100", description="Which GPU to use for this tool", exclude=True)
    private: SkipJsonSchema[bool] = Field(False, description="Tool is private from API", exclude=True)
    parameters: List[ToolParameter]

    def __init__(self, data, key):
        super().__init__(**data, key=key)

    def get_base_model(self, **kwargs):
        base_model = create_tool_base_model(self)
        return base_model(**kwargs)

    def summary(self, include_params=True, include_requirements=False):
        summary = f'"{self.key}" :: {self.name} - {self.description}.'
        if self.tip:
            summary += f" {self.tip}."
        if include_requirements:
            required_params = [f"{p.label} ({p.type})" for p in self.parameters if p.required]
            if required_params:
                summary += f" Required inputs: {', '.join(required_params)}."
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

    def get_info(self, include_params=True):
        data = {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "outputType": self.output_type
        } 
        if include_params:
            data["tip"] = self.tip
            data["parameters"] = [p.model_dump(exclude="comfyui") for p in self.parameters]
        return data

    def anthropic_tool_schema(self):
        tool_model = create_tool_base_model(self)
        schema = openai_schema(tool_model).anthropic_schema
        schema["input_schema"].pop("description") # duplicate
        return schema

    def openai_tool_schema(self):
        tool_model = create_tool_base_model(self)
        return {
            "type": "function",
            "function": openai_schema(tool_model).openai_schema
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
        root_dir = "../workflows" if self.key not in ["xhibit/vton", "xhibit/remix", "beeple_ai"] else "../private_workflows"  # todo: make this more robust
        args = json.loads(open(f"{root_dir}/{self.key}/test.json", "r").read())
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
    try:
        data = yaml.safe_load(open(api_path, "r"))
    except yaml.YAMLError as e:
        raise ValueError(f"Error loading {api_path}: {e}")
    if data['handler'] == 'comfyui':
        tool = ComfyUITool(data, key=name)
    elif data['handler'] == 'replicate':
        tool = ReplicateTool(data, key=name)
    else:
        tool = ModalTool(data, key=name)
    return tool


def get_tools(tools_folder: str, exclude: List[str] = []):
    required_files = {'api.yaml', 'test.json'}
    tools = {}
    exclude_set = set(exclude) | {"_dev"}  # exclude worklows/_dev folder 
    for root, dirs, files in os.walk(tools_folder):
        dirs[:] = [d for d in dirs if os.path.relpath(os.path.join(root, d), start=tools_folder) not in exclude_set]
        name = os.path.relpath(root, start=tools_folder)
        if "." in name or name in exclude_set or not required_files <= set(files):
            continue
        tools[name] = load_tool(os.path.join(tools_folder, name), name)
    return tools


def get_tools_summary(tools: List[Tool], include_params=False, include_requirements=False):    
    tools_summary = ""
    for tool in tools.values():
        tools_summary += f"{tool.summary(include_params=include_params, include_requirements=include_requirements)}\n"
    return tools_summary


def get_human_readable_error(error_list):
    # print("error_list", error_list)
    errors = []
    for error in error_list:
        field = error['loc'][0]
        error_type = error['type']
        input_value = error['input']
        if error_type == 'string_type':
            errors.append(f"{field} is missing")
        elif error_type == 'list_type':
            msg = error['msg']
            errors.append(f"{field}: {msg}")
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


class ModalTool(Tool):

    def submit(self, task: Task):
        task.args = self.prepare_args(task.args)
        function = modal.Function.lookup("handlers", "submit")
        job = function.spawn(self.key, task.to_mongo())
        return job.object_id

    def run(self, args: Dict):
        return asyncio.run(self.async_run(args))

    async def async_run(self, args: Dict, mock=False):
        args = self.prepare_args(args)
        if mock:
            return mock_image(args)
        function = modal.Function.lookup("handlers", "run")
        result = await function.remote.aio(self.key, args)
        return result
    
    def cancel(self, task: Task):
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        fc.cancel()
        task.status = "cancelled"
        task.save()


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
        cls = modal.Cls.lookup(app_name, self.key)
        job = cls().api.spawn(task.to_mongo())
        return job.object_id

    def run(self, args: Dict, app_name=DEFAULT_APP_NAME):
        return asyncio.run(self.async_run(args, app_name))

    async def async_run(self, args: Dict, mock=False, app_name=DEFAULT_APP_NAME):
        args = self.prepare_args(args)
        if mock:
            return mock_image(args)
        cls = modal.Cls.lookup(app_name, self.key)
        result = await cls().run.remote.aio(args)
        return result
    
    def cancel(self, task: Task):
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        fc.cancel()
        task.status = "cancelled"
        task.save()


class ReplicateTool(Tool):
    model: str
    output_handler: str = "normal"

    def _format_args_for_replicate(self, args):
        new_args = args.copy()
        for param in self.parameters:
            if param.type in ARRAY_TYPES:
                new_args[param.name] = "|".join([str(p) for p in args[param.name]])
        return new_args

    def _get_webhook_url(self):
        env = "tools" if os.getenv("ENV").lower() == "prod" else "tools-dev"
        dev = "-dev" if os.getenv("MODAL_SERVE") == "1" else ""
        webhook_url = f"https://edenartlab--{env}-fastapi-app{dev}.modal.run/update"
        return webhook_url
    
    def _create_prediction(self, args: dict, webhook=True):
        import replicate
        user, model = self.model.split('/', 1)
        model, version = model.split(':', 1)
        webhook_url = self._get_webhook_url() if webhook else None
        webhook_events_filter = ["start", "completed"] if webhook else None
        
        if version == "deployment":
            deployment = replicate.deployments.get(f"{user}/{model}")
            prediction = deployment.predictions.create(
                input=args,
                webhook=webhook_url,
                webhook_events_filter=webhook_events_filter
            )
        else:
            model = replicate.models.get(f"{user}/{model}")
            version = model.versions.get(version)
            prediction = replicate.predictions.create(
                version=version,
                input=args,
                webhook=webhook_url,
                webhook_events_filter=webhook_events_filter
            )
        return prediction

    def submit(self, task: Task):
        task.args = self.prepare_args(task.args)
        args = self._format_args_for_replicate(task.args)
        prediction = self._create_prediction(args)
        return prediction.id
    
    def run(self, args: Dict):
        return asyncio.run(self.async_run(args))

    async def async_run(self, args: Dict, mock=False):
        args = self.prepare_args(args)
        args = self._format_args_for_replicate(args)
        if mock:
            return mock_image(args)
        prediction = self._create_prediction(args, webhook=False)
        prediction.wait()        
        result = list(prediction.output)
        return result
    
    def cancel(self, task: Task):
        import replicate
        prediction = replicate.predictions.get(task.handler_id)
        prediction.cancel()
        task.status = "cancelled"
        task.save()
