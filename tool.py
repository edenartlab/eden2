import re
import os
import yaml
import json
import random
import asyncio
import modal
from enum import Enum
from datetime import datetime
from typing import Any, Tuple, Dict, List, Optional, Type, Literal
from pydantic import BaseModel, Field, ValidationError, create_model
from pydantic.json_schema import SkipJsonSchema
from instructor.function_calls import openai_schema

from models import Task, Model, User
from models import Story3 as Story
import eden_utils
import s3
import gcp


env = os.getenv("ENV", "STAGE")

TYPE_MAPPING = {
    "bool": bool, "string": str, "int": int, "float": float, 
    "image": str, "video": str, "audio": str, "zip": str, "lora": str, 
    "image|video": str,
    "dict": dict,
    "message": str,
}

class ParameterType(str, Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    IMAGE = "image"
    VIDEO = "video"
    IMAGE_VIDEO = "image|video"
    AUDIO = "audio"
    ZIP = "zip"
    LORA = "lora"
    BOOL_ARRAY = "bool[]"
    INT_ARRAY = "int[]"
    FLOAT_ARRAY = "float[]"
    STRING_ARRAY = "string[]"
    IMAGE_ARRAY = "image[]"
    VIDEO_ARRAY = "video[]"
    IMAGE_VIDEO_ARRAY = "image|video[]"
    AUDIO_ARRAY = "audio[]"
    ZIP_ARRAY = "zip[]"
    LORA_ARRAY = "lora[]"
    DICT = "dict"
    MESSAGE = "message"

FILE_TYPES = [
    ParameterType.IMAGE, ParameterType.VIDEO, ParameterType.AUDIO
]

FILE_ARRAY_TYPES = [
    ParameterType.IMAGE_ARRAY, ParameterType.VIDEO_ARRAY, ParameterType.IMAGE_VIDEO, ParameterType.AUDIO_ARRAY
]

ARRAY_TYPES = [
    ParameterType.BOOL_ARRAY, ParameterType.INT_ARRAY, ParameterType.FLOAT_ARRAY, ParameterType.STRING_ARRAY, 
    ParameterType.IMAGE_ARRAY, ParameterType.VIDEO_ARRAY, ParameterType.IMAGE_VIDEO_ARRAY, ParameterType.AUDIO_ARRAY, ParameterType.LORA_ARRAY, ParameterType.ZIP_ARRAY
]


class ToolParameter(BaseModel):
    name: str
    label: str
    description: str = Field(None, description="Human-readable description of what parameter does")
    tip: str = Field(None, description="Additional tips for a user or LLM on how to use this parameter properly")
    type: ParameterType
    keys: Optional[List[Dict[str, Any]]] = Field(None, description="Keys for dict type")
    required: bool = Field(False, description="Indicates if the field is mandatory")
    visible_if: str = Field(None, description="Condition under which parameter is visible to UI")
    hide_from_agent: bool = Field(False, description="Hide from agent/assistant")
    hide_from_ui: bool = Field(False, description="Hide from UI")
    default: Optional[Any] = Field(None, description="Default value")
    minimum: Optional[float] = Field(None, description="Minimum value for int or float type")
    maximum: Optional[float] = Field(None, description="Maximum value for int or float type")
    step: Optional[float] = Field(None, description="Step size for number ranges")
    min_length: Optional[int] = Field(None, description="Minimum length for array type")
    max_length: Optional[int] = Field(None, description="Maximum length for array type")
    choices: Optional[List[Any]] = Field(None, description="Allowed values")
    choice_labels: Optional[List[Any]] = Field(None, description="Labels for choices")


class Tool(BaseModel):
    key: str
    name: str
    thumbnail: Optional[str] = Field(None, description="URL to a thumbnail image")
    description: str = Field(..., description="Human-readable description of what the tool does")
    tip: Optional[str] = Field(None, description="Additional tips for a user or LLM on how to get what they want out of this tool")
    cost_estimate: str = Field(None, description="A formula which estimates the inference cost as a function of the parameters")
    output_type: ParameterType = Field(None, description="Output type from the tool")
    resolutions: Optional[List[str]] = Field(None, description="List of allowed resolution labels")
    gpu: SkipJsonSchema[Optional[str]] = Field("A100", description="Which GPU to use for this tool", exclude=True)
    test_args: SkipJsonSchema[Optional[dict]] = Field({}, description="Test args", exclude=True)
    private: SkipJsonSchema[bool] = Field(False, description="Tool is private from API")
    handler: SkipJsonSchema[str] = Field(False, description="Which type of tool", exclude=True)
    parameters: List[ToolParameter]

    def __init__(self, data, key):
        super().__init__(**data, key=key)

    def get_base_model(self, **kwargs):
        base_model = create_tool_base_model(self)
        return base_model(**kwargs)
    
    def summary(self, include_params=True, include_requirements=False):
        summary = f'"{self.key}" :: {self.name} - '
        summary += eden_utils.concat_sentences(self.description, self.tip)
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
            summary += f"\n{param.name}: {param.label}, "
            summary += eden_utils.concat_sentences(param.description, param.tip)
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

    def get_interface(self, include_params=True):
        data = {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "thumbnail": self.thumbnail,
            "outputType": self.output_type,
            "resolutions": self.resolutions,
            "costEstimate": self.cost_estimate,
            "private": self.private
        } 
        if hasattr(self, "base_model"):
            data["baseModel"] = self.base_model
        if include_params:
            data["tip"] = self.tip
            data["parameters"] = [p.model_dump(exclude="comfyui") for p in self.parameters]
        return data

    def anthropic_tool_schema(self, remove_hidden_fields=False, include_tips=False):
        tool_model = create_tool_base_model(self, remove_hidden_fields=remove_hidden_fields, include_tips=include_tips)
        schema = openai_schema(tool_model).anthropic_schema
        schema["input_schema"].pop("description")  # duplicated
        schema = self.expand_schema_for_dicts(schema, provider="anthropic")
        return schema

    def openai_tool_schema(self, remove_hidden_fields=False, include_tips=False):
        tool_model = create_tool_base_model(self, remove_hidden_fields=remove_hidden_fields, include_tips=include_tips)
        schema = openai_schema(tool_model).openai_schema
        schema = self.expand_schema_for_dicts(schema, provider="openai")
        return {
            "type": "function",
            "function": schema
        }

    def expand_schema_for_dicts(self, schema, provider=Literal["openai", "anthropic"]):
        for param in self.parameters:
            if param.type == ParameterType.DICT:
                sub_schema = {
                    "type": "object",
                    "properties": {}
                }
                for key in param.keys:
                    is_list = key['type'].endswith('[]')
                    field_type = key['type'].rstrip('[]')
                    is_dict = field_type == "dict"
                    if is_list:
                        sub_schema["properties"][key['name']] = {
                            "type": "array",
                            "items": {
                                "type": field_type
                            },
                            "minItems": 1,
                            "title": key['name'],
                            "description": key['description']
                        }
                    else:
                        sub_schema["properties"][key['name']] = {
                            "type": key['type'],
                            "title": key['name'],
                            "description": key['description']
                        }
                if provider == "anthropic" and schema['input_schema']['properties'].get(param.name):
                    schema['input_schema']['properties'][param.name] = sub_schema
                elif provider == "openai" and schema['parameters']['properties'].get(param.name):
                    schema['parameters']['properties'][param.name] = sub_schema
        return schema

    def prepare_args(self, user_args):
        args = {}
        for param in self.parameters:
            key = param.name
            value = None
            if param.default is not None:
                value = param.default
            if user_args.get(key) is not None:
                value = user_args[key]
            if value == "random":
                value = random.randint(param.minimum, param.maximum)
            args[key] = value

        unrecognized_args = set(user_args.keys()) - {param.name for param in self.parameters}
        if unrecognized_args:
            raise ValueError(f"Unrecognized arguments provided: {', '.join(unrecognized_args)}")

        try:
            create_tool_base_model(self)(**args, include_tips=True)  # validate args
        except ValidationError as e:
            error_str = get_human_readable_error(e.errors())
            raise ValueError(error_str)

        return args

    def get_user_result(self, result):
        # if isinstance(result, str) or isinstance(result, list):
            # return result
        for r in result:
            if "filename" in r:
                filename = r.pop("filename")
                r["url"] = f"{s3.get_root_url(env=env)}/{filename}"
            if "model" in r:
                r["model"] = str(r["model"])
                r.pop("metadata")  # don't need to return model metadata here
        return result
    
    def handle_run(run_function):
        async def wrapper(self, args: Dict, *args_, **kwargs):
            args = self.prepare_args(args)
            result = await run_function(self, args, *args_, **kwargs)
            return self.get_user_result(result)
        return wrapper

    def calculate_cost(self, args):
        if not self.cost_estimate:
            return 0
        cost_formula = re.sub(r'(\w+)\.length', r'len(\1)', self.cost_estimate) # js to py
        cost_estimate = eval(cost_formula, args)
        assert isinstance(cost_estimate, (int, float)), "Cost estimate not a number"
        return cost_estimate

    def handle_submit(submit_function):
        async def wrapper(self, task: Task, *args, **kwargs):
            user = User.from_id(task.user, env=env)
            task.args = self.prepare_args(task.args)
            task.cost = self.calculate_cost(task.args.copy())
            user.verify_manna_balance(task.cost)
            task.status = "pending"
            task.save()
            handler_id = await submit_function(self, task, *args, **kwargs)
            task.update({"handler_id": handler_id})
            user.spend_manna(task.cost)
            return handler_id
        return wrapper

    def handle_cancel(cancel_function):
        async def wrapper(self, task: Task):
            await cancel_function(self, task)
            n_samples = task.args.get("n_samples", 1)
            refund_amount = (task.cost or 0) * (n_samples - len(task.result or [])) / n_samples
            user = User.from_id(task.user, env=env)
            user.refund_manna(refund_amount)
            task.status = "cancelled"
            task.save()
        return wrapper

    async def async_submit_and_run(self, task: Task):
        await self.async_submit(task)
        result = await self.async_process(task)
        return result 

    def run(self, args: Dict):
        return asyncio.run(self.async_run(args))

    def submit(self, task: Task):
        return asyncio.run(self.async_submit(task))

    def submit_and_run(self, task: Task):
        return asyncio.run(self.async_submit_and_run(task))
    
    def cancel(self, task: Task):
        return asyncio.run(self.async_cancel(task))


# class MongoTool(Tool):
#     object_type: str

#     @Tool.handle_run
#     async def async_run(self, args: Dict):
#         object_types = {"Story": Story}
#         document_id = args.pop("id")
#         if document_id:
#             document = object_types[self.object_type].from_id(document_id, env=env)
#         else:
#             document = object_types[self.object_type](env=env)
#         args = {k: v for k, v in args.items() if v is not None}
#         document.update_current(args)
#         result = {"document_id": str(document.id)}
#         return result

#     @Tool.handle_submit
#     async def async_submit(self, task: Task):
#         args = task.args
#         return "ok"
    
#     async def async_process(self, task: Task):
#         # if not task.handler_id:
#         #     task.reload()
#         # fc = modal.functions.FunctionCall.from_id(task.handler_id)
#         # await fc.get.aio()
#         # task.reload()
#         return "ok"
#         #return self.get_user_result(task.result)

#     @Tool.handle_cancel
#     async def async_cancel(self, task: Task):
#         #fc = modal.functions.FunctionCall.from_id(task.handler_id)
#         #await fc.cancel.aio()
#         pass


class ModalTool(Tool):
    @Tool.handle_run
    async def async_run(self, args: Dict):
        func = modal.Function.lookup("handlers", "run")
        result = await func.remote.aio(self.key, args)
        return result

    @Tool.handle_submit
    async def async_submit(self, task: Task):
        func = modal.Function.lookup("handlers", "submit")
        job = func.spawn(str(task.id), env=env)
        return job.object_id
    
    async def async_process(self, task: Task):
        if not task.handler_id:
            task.reload()
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        await fc.get.aio()
        task.reload()
        return self.get_user_result(task.result)

    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        await fc.cancel.aio()



class ComfyUIParameterMap(BaseModel):
    input: str
    output: str

class ComfyUIRemap(BaseModel):
    node_id: int
    field: str
    subfield: str
    value: List[ComfyUIParameterMap]

class ComfyUIInfo(BaseModel):
    node_id: int
    field: str
    subfield: str
    preprocessing: Optional[str] = None
    remap: Optional[List[ComfyUIRemap]] = None

class ComfyUIParameter(ToolParameter):
    comfyui: Optional[ComfyUIInfo] = Field(None)

class ComfyUIIntermediateOutput(BaseModel):
    name: str
    node_id: int

class ComfyUITool(Tool):
    base_model: Optional[str] = Field("sdxl", description="Base model to use for ComfyUI", choices=["sdxl", "flux-dev", "flux-schnell"])
    parameters: List[ComfyUIParameter]
    comfyui_output_node_id: Optional[int] = Field(None, description="ComfyUI node ID of output media")
    comfyui_intermediate_outputs: Optional[List[ComfyUIIntermediateOutput]] = Field(None, description="Intermediate outputs from ComfyUI")
    workspace: str

    def __init__(self, data, key):
        super().__init__(data, key)

    @Tool.handle_run
    async def async_run(self, args: Dict):
        cls = modal.Cls.lookup(f"comfyui-{self.workspace}", "ComfyUI")
        result = await cls().run.remote.aio(self.key, args)
        return self.get_user_result(result)
        
    @Tool.handle_submit
    async def async_submit(self, task: Task):
        cls = modal.Cls.lookup(f"comfyui-{self.workspace}", "ComfyUI")
        job = await cls().run_task.spawn.aio(str(task.id), env=env)
        return job.object_id
    
    async def async_process(self, task: Task):
        if not task.handler_id:
            task.reload()
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        await fc.get.aio()
        task.reload()
        return self.get_user_result(task.result)

    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        await fc.cancel.aio()


class ReplicateParameter(ToolParameter):
    alias: Optional[str] = None

class ReplicateTool(Tool):
    model: str
    version: Optional[str] = Field(None, description="Replicate version to use")
    output_handler: str = "normal"
    parameters: List[ReplicateParameter]

    @Tool.handle_run
    async def async_run(self, args: Dict):
        import replicate
        args = self._format_args_for_replicate(args)
        if self.version:
            prediction = self._create_prediction(args, webhook=False)        
            prediction.wait()
            if self.output_handler == "eden":
                output = [prediction.output[-1]["files"][0]]
            elif self.output_handler == "trainer":
                output = [prediction.output[-1]["thumbnails"][0]]
            else:
                output = prediction.output if isinstance(prediction.output, list) else [prediction.output]
                output = [url for url in output]
        else:
            output = replicate.run(self.model, input=args)
        result = eden_utils.upload_media(output, env=env)
        return result

    @Tool.handle_submit
    async def async_submit(self, task: Task, webhook: bool = True):
        import replicate

        args = self._format_args_for_replicate(task.args)
        if self.version:
            prediction = self._create_prediction(args, webhook=webhook)
            return prediction.id
        else:
            # Replicate doesn't support spawning tasks for models without a version so just run it immediately
            output = replicate.run(self.model, input=task.args)
            replicate_update_task(task, "succeeded", None, output, "normal")
            handler_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=28))  # make up Replicate id
            return handler_id

    async def async_process(self, task: Task):
        import replicate

        if not task.handler_id:
            task.reload()

        if self.version is None:
            return self.get_user_result(task.result)        
        else:
            prediction = await replicate.predictions.async_get(task.handler_id)
            status = "starting"
            while True: 
                if prediction.status != status:
                    status = prediction.status
                    result = replicate_update_task(
                        task,
                        status, 
                        prediction.error, 
                        prediction.output, 
                        self.output_handler
                    )
                    if result["status"] in ["failed", "cancelled", "completed"]:
                        return self.get_user_result(result["result"])
                await asyncio.sleep(0.5)
                prediction.reload()

    async def async_submit_and_run(self, task: Task):
        await self.async_submit(task, webhook=False)
        result = await self.async_process(task)
        return result

    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        import replicate
        try:
            prediction = replicate.predictions.get(task.handler_id)
            prediction.cancel()
        except Exception as e:
            print("Replicate cancel error, probably task is timed out or already finished", e)

    def _format_args_for_replicate(self, args):
        new_args = args.copy()
        new_args = {k: v for k, v in new_args.items() if v is not None}
        for param in self.parameters:
            if param.type in ARRAY_TYPES:
                new_args[param.name] = "|".join([str(p) for p in args[param.name]])
            if param.alias:
                new_args[param.alias] = new_args.pop(param.name)
        return new_args

    def _get_webhook_url(self):
        env = "tools" if os.getenv("ENV") == "PROD" else "tools-dev"
        dev = "-dev" if os.getenv("ENV") == "STAGE" and os.getenv("MODAL_SERVE") == "1" else ""
        webhook_url = f"https://edenartlab--{env}-fastapi-app{dev}.modal.run/update"
        return webhook_url
    
    def _create_prediction(self, args: dict, webhook=True):
        import replicate
        user, model = self.model.split('/', 1)
        webhook_url = self._get_webhook_url() if webhook else None
        webhook_events_filter = ["start", "completed"] if webhook else None

        if self.version == "deployment":
            deployment = replicate.deployments.get(f"{user}/{model}")
            prediction = deployment.predictions.create(
                input=args,
                webhook=webhook_url,
                webhook_events_filter=webhook_events_filter
            )
        else:
            model = replicate.models.get(f"{user}/{model}")
            version = model.versions.get(self.version)
            prediction = replicate.predictions.create(
                version=version,
                input=args,
                webhook=webhook_url,
                webhook_events_filter=webhook_events_filter
            )
        return prediction


def replicate_update_task(task: Task, status, error, output, output_handler):
    if status == "failed":
        task.status = "error"
        task.error = error
        task.save()
        n_samples = task.args.get("n_samples", 1)
        refund_amount = (task.cost or 0) * (n_samples - len(task.result or [])) / n_samples
        user = User.from_id(task.user, env=env)
        user.refund_manna(refund_amount)
        return {"status": "failed", "error": error}
    
    elif status == "canceled":
        task.status = "cancelled"
        task.save()
        n_samples = task.args.get("n_samples", 1)
        refund_amount = (task.cost or 0) * (n_samples - len(task.result or [])) / n_samples
        user = User.from_id(task.user, env=env)
        user.refund_manna(refund_amount)
        return {"status": "cancelled"}
    
    elif status == "processing":
        task.performance["waitTime"] = (datetime.utcnow() - task.createdAt).total_seconds()
        task.status = "running"
        task.save()
        return {"status": "running"}
    
    elif status == "succeeded":
        if output_handler == "normal":
            output = output if isinstance(output, list) else [output]
            result = eden_utils.upload_media(output, env=env)
        
        elif output_handler in ["trainer", "eden"]:
            result = replicate_process_eden(output)

            if output_handler == "trainer":
                filename = result[0]["filename"]
                thumbnail = result[0]["thumbnail"]
                url = f"{s3.get_root_url(env=env)}/{filename}"
                model = Model(
                    name=task.args["name"],
                    user=task.user,
                    args=task.args,
                    task=task.id,
                    checkpoint=url, 
                    base_model="sdxl",
                    thumbnail=thumbnail,
                    env=env
                )
                model.save({"task": task.id})
                result[0]["model"] = model.id
        
        run_time = (datetime.utcnow() - task.createdAt).total_seconds()
        if task.performance.get("waitTime"):
            run_time -= task.performance["waitTime"]
        task.performance["runTime"] = run_time
        
        task.status = "completed"
        task.result = result
        task.save()

        return {
            "status": "completed", 
            "result": result
        }


def replicate_process_eden(output):
    output = output[-1]
    if not output or "files" not in output:
        raise Exception("No output found")         

    results = []
    
    for file, thumb in zip(output["files"], output["thumbnails"]):
        file_url, _ = s3.upload_file_from_url(file, env=env)
        filename = file_url.split("/")[-1]
        metadata = output.get("attributes")
        media_attributes, thumbnail = eden_utils.get_media_attributes(file_url)

        result = {
            "filename": filename,
            "metadata": metadata,
            "mediaAttributes": media_attributes
        }

        thumbnail = thumbnail or thumb or None
        if thumbnail:
            #thumbnail_url, _ = s3.upload_file_from_url(thumbnail, file_type='.webp', env=env)
            thumbnail_result = eden_utils.upload_media([thumbnail], env=env)
            result["thumbnail"] = thumbnail_result[0]['filename']

        results.append(result)

    return results
    

def create_tool_base_model(tool: Tool, remove_hidden_fields=False, include_tips=False):
    fields = {
        param.name: get_field_type_and_kwargs(param, remove_hidden_fields=remove_hidden_fields, include_tip=include_tips)
        for param in tool.parameters
    }
    ToolBaseModel = create_model(tool.key, **fields)
    ToolBaseModel.__doc__ = eden_utils.concat_sentences(tool.description, tool.tip)
    return ToolBaseModel


def get_field_type_and_kwargs(
    param: ToolParameter,
    remove_hidden_fields: bool = False,
    include_tip: bool = False
) -> Tuple[Type, Dict[str, Any]]:
    field_kwargs = {
        'description': eden_utils.concat_sentences(param.description, param.tip) \
            if include_tip else param.description
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

    if remove_hidden_fields and param.hide_from_agent:
        field_type = SkipJsonSchema[field_type]
    
    return (field_type, Field(**field_kwargs))


def load_tool(tool_path: str, name: str = None) -> Tool:
    api_path = f"{tool_path}/api.yaml"
    if not os.path.exists(api_path):
        raise ValueError(f"Tool {name} not found at {api_path}")
    if name is None:
        name = os.path.relpath(tool_path, start=os.path.dirname(tool_path))
    try:
        data = yaml.safe_load(open(api_path, "r"))
        if data.get('cost_estimate'):
            data['cost_estimate'] = str(data['cost_estimate'])
    except yaml.YAMLError as e:
        raise ValueError(f"Error loading {api_path}: {e}")

    if 'parent_tool' in data:
        parent_tool_path = data['parent_tool']
        tool = PresetTool(data, key=name, parent_tool_path=parent_tool_path)
    elif data['handler'] == 'comfyui':
        data["workspace"] = tool_path.split("/")[-3]
        tool = ComfyUITool(data, key=name) 
    # elif data['handler'] == 'mongo':
    #     tool = MongoTool(data, key=name)
    elif data['handler'] == 'replicate':
        tool = ReplicateTool(data, key=name)
    elif data['handler'] == 'gcp':
        tool = GCPTool(data, key=name)
    else:
        tool = ModalTool(data, key=name)
    tool.test_args = json.loads(open(f"{tool_path}/test.json", "r").read())
    return tool


def get_tools(tools_folder: str):
    required_files = {'api.yaml', 'test.json'}
    tools = {}
    for root, dirs, files in os.walk(tools_folder):
        name = os.path.relpath(root, start=tools_folder)
        if "." in name or not required_files <= set(files):
            continue
        tools[name] = load_tool(os.path.join(tools_folder, name), name)
    return tools


def get_comfyui_tools(envs_dir: str):
    return {
        k: v for env in os.listdir(envs_dir) 
        for k, v in get_tools(f"{envs_dir}/{env}/workflows").items()
    }


def get_tools_summary(tools: List[Tool], include_params=False, include_requirements=False):    
    tools_summary = ""
    for tool in tools.values():
        tools_summary += f"{tool.summary(include_params=include_params, include_requirements=include_requirements)}\n"
    return tools_summary


def get_human_readable_error(error_list):
    errors = []
    for error in error_list:
        field = error['loc'][0]
        error_type = error['type']
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
            errors.append(f"{field} must be <= {max_value}")
        elif error_type == 'greater_than_equal':
            min_value = error['ctx']['ge']
            errors.append(f"{field} must be >= {min_value}")
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


class GCPTool(Tool):
    gcr_image_uri: str
    machine_type: str
    gpu: str
    
    # Todo: make work without task ID
    @Tool.handle_run
    async def async_run(self, args: Dict):
        raise NotImplementedError("Not implemented yet, need a Task ID")
        
    @Tool.handle_submit
    async def async_submit(self, task: Task):
        handler_id = gcp.submit_job(
            gcr_image_uri=self.gcr_image_uri,
            machine_type=self.machine_type,
            gpu=self.gpu,
            gpu_count=1,
            task_id=str(task.id),
            env=env
        )
        return handler_id
    
    async def async_process(self, task: Task):
        if not task.handler_id:
            task.reload()
        await gcp.poll_job_status(task.handler_id)
        task.reload()
        return self.get_user_result(task.result)

    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        await gcp.cancel_job(task.handler_id)




class PresetTool(Tool):
    parent_tool: Tool

    def __init__(self, data, key, parent_tool_path):
        parent_data = self.load_parent_tool(parent_tool_path)
        merged_data = self.merge_parent_data(parent_data, data)
        
        merged_data["parent_tool"] = load_tool(parent_tool_path)

        # Initialize as a Tool using the merged data
        super().__init__(merged_data, key)

        
        print("THE TYPE", type(self.parent_tool))

    @staticmethod
    def load_parent_tool(parent_tool_path: str) -> dict:
        api_path = f"{parent_tool_path}/api.yaml"
        if not os.path.exists(api_path):
            raise ValueError(f"Parent tool not found at {api_path}")
        try:
            parent_data = yaml.safe_load(open(api_path, "r"))
        except yaml.YAMLError as e:
            raise ValueError(f"Error loading parent tool {api_path}: {e}")
        return parent_data

    def merge_parent_data(self, parent_data: dict, preset_data: dict) -> dict:
        # Create a copy of parent_data to avoid modifying the original
        merged_data = parent_data.copy()
        
        # Update with preset data
        for key, value in preset_data.items():
            if key == "parameters" and value is not None:
                # Update specific parameter fields if provided in preset
                parent_params = {p['name']: p for p in merged_data.get('parameters', [])}
                preset_params = value
                
                for param in preset_params:
                    if param['name'] in parent_params:
                        # Update existing parameter with preset fields
                        parent_params[param['name']].update(param)
                    else:
                        raise ValueError(f"Parameter {param['name']} not found in parent tool")
                
                merged_data['parameters'] = list(parent_params.values())
            else:
                # Override other fields directly
                merged_data[key] = value

        return merged_data
    

    async def async_run(self, args: Dict):
        return await self.parent_tool.async_run(args)
        
    @Tool.handle_submit
    async def async_submit(self, task: Task):
        return await self.parent_tool.async_submit(task)
    
    async def async_process(self, task: Task):
        return await self.parent_tool.async_process(task)

    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        return await self.parent_tool.async_cancel(task)
