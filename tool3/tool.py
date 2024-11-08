import os
import re
import copy
import yaml
import json
import random
import asyncio
import eden_utils
from pprint import pprint
from pydantic import BaseModel, Field, create_model, ValidationError
from typing import Optional, List, Dict, Any, Type, Literal

import eden_utils
from base import parse_schema
from models import Task, User
from mongo import MongoModel, get_collection


# class Tool(MongoModel):
class Tool(BaseModel):
    """
    Base class for all tools.
    """

    key: str
    name: str
    description: str
    tip: Optional[str] = None
    cost_estimate: str
    output_type: Literal["bool", "str", "int", "float", "string", "image", "video", "audio", "lora"]
    resolutions: Optional[List[str]] = None
    base_model: Optional[str] = "sdxl"
    gpu: Optional[str] = None    
    status: Optional[Literal["inactive", "stage", "prod"]] = "stage"
    allowlist: Optional[str] = None
    visible: Optional[bool] = True
    test_args: Dict[str, Any]
    handler: Literal["local", "modal", "comfyui", "replicate", "gcp"] = "local"
    # base_model: Type[BaseModel] = Field(None, exclude=True)
    base_model: Type[BaseModel] = None


    # do somethig about base_model BaseModel and "sdxl"

    parent_tool: Optional[str] = None

    # @classmethod
    # def get_collection_name(cls) -> str:
    #     return "tools2"

    @classmethod
    def _create_tool(cls, key: str, schema: dict, test_args: dict, env: str, **kwargs):
        fields = parse_schema(schema)
        base_model = create_model(key, **fields)
        base_model.__doc__ = eden_utils.concat_sentences(schema.get('description'), schema.get('tip', ''))

        tool_data = {k: schema.pop(k) for k in cls.model_fields.keys() if k in schema}
        tool_data['test_args'] = test_args
        tool_data['base_model'] = base_model
        
        if 'cost_estimate' in tool_data:
            tool_data['cost_estimate'] = str(tool_data['cost_estimate'])
            
        return cls(env=env, key=key, **tool_data, **kwargs)

    @classmethod
    def from_dir(cls, env: str, tool_dir: str, **kwargs):
        key = tool_dir.split('/')[-1]
        yaml_file = os.path.join(tool_dir, 'api.yaml')
        test_file = os.path.join(tool_dir, 'test.json')

        with open(yaml_file, 'r') as f:
            schema = yaml.safe_load(f)
                
        with open(test_file, 'r') as f:
            test_args = json.load(f)

        return cls._create_tool(key, schema, test_args, env, **kwargs)

    @classmethod
    def from_mongo(cls, key: str, env: str, **kwargs):
        tools = get_collection("tools2", env=env)
        schema = tools.find_one({"key": key})
        key = schema.pop('key')
        test_args = schema.pop('test_args')

        return cls._create_tool(key, schema, test_args, env, **kwargs)
        
    @classmethod
    def from_preset(cls, preset_tool, schema: dict, test_args: dict) -> 'Tool':
        """Create a new tool instance from a preset (parent) tool."""
        tool_class = type(preset_tool)
        preset_data = preset_tool.model_dump()
        base_model = preset_tool.base_model

        # Update base model parameters
        for key, parameter in schema.pop("parameters", {}).items():
            if key not in base_model.model_fields:
                raise ValueError(f"Parameter {key} not found in base model")
            for attr_name, attr_value in parameter.items():
                if hasattr(base_model.model_fields[key], attr_name):
                    setattr(base_model.model_fields[key], attr_name, attr_value)

        # Update preset data with new schema values
        preset_data.update(schema)
        preset_data['test_args'] = test_args
        preset_data['base_model'] = base_model
        preset_data['description'] = eden_utils.concat_sentences(
            schema.get('description', preset_data.get('description')), 
            schema.get('tip', preset_data.get('tip'))
        )
    
        return tool_class.model_validate(preset_data)

    def calculate_cost(self, args):
        if not self.cost_estimate:
            return 0
        cost_formula = self.cost_estimate
        cost_formula = re.sub(r'(\w+)\.length', r'len(\1)', cost_formula)  # Array length
        cost_formula = re.sub(r'(\w+)\s*\?\s*([^:]+)\s*:\s*([^,\s]+)', r'\2 if \1 else \3', cost_formula)  # Ternary operator
        
        cost_estimate = eval(cost_formula, args)
        assert isinstance(cost_estimate, (int, float)), "Cost estimate not a number"
        return cost_estimate

    def prepare_args(self, args: dict):
        unrecognized_args = set(args.keys()) - set(self.base_model.model_fields.keys())
        if unrecognized_args:
            raise ValueError(f"Unrecognized arguments provided: {', '.join(unrecognized_args)}")

        prepared_args = {}
        for field, field_info in self.base_model.model_fields.items():
            if field in args:
                prepared_args[field] = args[field]
            elif field_info.default is not None:
                if field_info.default == "random":
                    minimum, maximum = field_info.metadata[0].ge, field_info.metadata[1].le
                    prepared_args[field] = random.randint(minimum, maximum)
                else:
                    prepared_args[field] = field_info.default
            else:
                prepared_args[field] = None
        
        try:
            self.base_model(**prepared_args)
        except ValidationError as e:
            error_str = eden_utils.get_human_readable_error(e.errors())
            raise ValueError(error_str)

        return prepared_args

    def handle_run(run_function):
        async def wrapper(self, args: Dict, env: str):
            try:
                args = self.prepare_args(args)
                result = await run_function(self, args, env)
            except Exception as e:
                result = {"error": str(e)}
            return eden_utils.prepare_result(result, env)
        return wrapper

    def handle_start_task(start_task_function):
        async def wrapper(self, user_id: str, args: Dict, env: str):
            # validate args and user manna balance
            args = self.prepare_args(args)
            cost = self.calculate_cost(args.copy())
            user = User.load(user_id, env=env)
            user.verify_manna_balance(cost)            
            
            # create task and set pending
            task = Task(
                env=env, 
                workflow=self.key, 
                output_type=self.output_type, 
                args=args, 
                user=user_id, 
                cost=cost
            )
            task.save()            
            
            try:
                # run task and spend manna
                handler_id = await start_task_function(self, task)
                task.update(handler_id=handler_id)
                user.spend_manna(task.cost)            
            except Exception as e:
                task.update(status="failed", error=str(e))
                raise Exception(f"Task failed: {e}. No manna deducted.")
            
            return task

        return wrapper
    
    def handle_wait(wait_function):
        async def wrapper(self, task: Task):
            if not task.handler_id:
                task.reload()
            try:
                result = await wait_function(self, task)
            except Exception as e:
                result = {"status": "failed", "error": str(e)}
            return eden_utils.prepare_result(result, task.env)
        return wrapper
    
    def handle_cancel(cancel_function):
        async def wrapper(self, task: Task):
            await cancel_function(self, task)
            n_samples = task.args.get("n_samples", 1)
            refund_amount = (task.cost or 0) * (n_samples - len(task.result or [])) / n_samples
            user = User.from_id(task.user, env=task.env)
            user.refund_manna(refund_amount)
            task.update(status="cancelled")
        return wrapper

    @property
    def async_run(self):
        raise NotImplementedError("Subclasses must implement async_run")

    @property 
    def async_start_task(self):
        raise NotImplementedError("Subclasses must implement async_start_task")

    @property
    def async_wait(self):
        raise NotImplementedError("Subclasses must implement async_wait")

    @property
    def async_cancel(self):
        raise NotImplementedError("Subclasses must implement async_cancel")

    def run(self, args: Dict, env: str):
        return asyncio.run(self.async_run(args, env))

    def start_task(self, task: Task):
        return asyncio.run(self.async_start_task(task))

    def wait(self, task: Task):
        return asyncio.run(self.async_wait(task))

    def cancel(self, task: Task):
        return asyncio.run(self.async_cancel(task))
    


def load_tool_from_mongo(key: str, env: str, prefer_local: bool = True) -> Tool:
    """Load the tool class based on the handler in api.yaml"""
    
    tools = get_collection("tools2", env=env)
    schema = tools.find_one({"key": key})
    key = schema.pop('key')

    tool_class = _get_tool_class(schema, prefer_local)
    return tool_class.from_mongo(key=key, env=env)


def load_tool_from_dir(tool_dir: str, env: str, prefer_local: bool = True) -> Tool:
    """Load the tool class based on the handler in api.yaml"""
    
    api_file = os.path.join(tool_dir, 'api.yaml')
    with open(api_file, 'r') as f:
        schema = yaml.safe_load(f)

    if schema.get("parent_tool"):
        tool_dirs = sum([_get_tool_dirs(path) for path in ["tools", "../../workflows"]], [])
        tool_dirs = {tool_dir.split("/")[-1]: tool_dir for tool_dir in tool_dirs}
        
        if schema["parent_tool"] not in tool_dirs:
            raise ValueError(f"Parent tool {schema['parent_tool']} not found in tool_dirs")
        
        parent_tool = load_tool_from_dir(tool_dir=tool_dirs[schema["parent_tool"]], env=env)
        
        test_args_file = os.path.join(tool_dir, 'test.json')
        with open(test_args_file, 'r') as f:
            test_args = json.load(f)

        schema['key'] = tool_dir.split("/")[-1]
        return Tool.from_preset(parent_tool, schema, test_args)
    else:
        tool_class = _get_tool_class(schema, prefer_local)
        return tool_class.from_dir(tool_dir=tool_dir, env=env)


def save_tool(tool_dir: str, env: str) -> Tool:
    """Save tool to mongo"""
    
    api_file = os.path.join(tool_dir, 'api.yaml')
    with open(api_file, 'r') as f:
        schema = yaml.safe_load(f)

    key = tool_dir.split("/")[-1]
    schema["key"] = key
    if schema.get("handler") == "comfyui":
        schema["workspace"] = tool_dir.split('/')[-3]

    test_args_file = os.path.join(tool_dir, 'test.json')
    with open(test_args_file, 'r') as f:
        schema["test_args"] = json.load(f)

    tools = get_collection("tools2", env=env)
    tools.replace_one({"key": key}, schema, upsert=True)


def _get_tool_dirs(path: str) -> List[str]:
    """Get all tool directories inside a directory"""
    
    tool_dirs = []
    
    for root, _, files in os.walk(path):
        if "api.yaml" in files and "test.json" in files:
            tool_dirs.append(os.path.relpath(root))
            
    return tool_dirs


def get_tools_from_dir(path: str, env: str, include_inactive: bool = False) -> Dict[str, Tool]:
    """Get all tools inside a directory"""
    
    tools = {}

    tool_dirs = _get_tool_dirs(path)
    print("ALL THE TOOL DIRS", tool_dirs)


    for tool_dir in tool_dirs:
        tool = load_tool_from_dir(tool_dir, env=env)
        if tool.status != "inactive" and not include_inactive:
            print("THIS IS THE TOOL PARENT", tool.key, tool.parent_tool)
            # key = tool.parent_tool or tool.key
            if tool.key in tools:
                raise ValueError(f"Duplicate tool {tool.key} found.")
            tools[tool.key] = tool
        
    return tools

def get_tools_from_mongo(env: str, include_inactive: bool = False) -> Dict[str, Tool]:
    """Get all tools from mongo"""
    
    tools = {}
    tools_collection = get_collection("tools2", env=env)
    for tool in tools_collection.find():
        tool = load_tool_from_mongo(tool['key'], env=env)
        if tool.status != "inactive" and not include_inactive:
            if tool.key in tools:
                raise ValueError(f"Duplicate tool {tool.key} found.")
            tools[tool.key] = tool
        
    return tools


def save_tools(tools: List[str] = None, env: str = "STAGE") -> Dict[str, Tool]:
    """Get all tools inside a directory"""
    
    tool_dirs = []
    for path in ["tools", "../../workflows"]:
        tool_dirs += _get_tool_dirs(path, env=env)
    
    for tool_dir in tool_dirs:
        key = tool_dir.split("/")[-1]
        if tools and key not in tools:
            continue
        save_tool(tool_dir, env=env)
        
    return tools


def _get_tool_class(schema: dict, prefer_local: bool = True):
    from comfyui_tool import ComfyUITool
    from replicate_tool import ReplicateTool
    from modal_tool import ModalTool
    from gcp_tool import GCPTool
    from local_tool import LocalTool

    handler = schema.get('handler')
    handler_map = {
        "comfyui": ComfyUITool,
        "replicate": ReplicateTool,
        "modal": ModalTool,
        "gcp": GCPTool,
        "local": LocalTool,
        None: LocalTool if prefer_local else ModalTool
    }
    
    tool_class = handler_map.get(handler, Tool)
    return tool_class
    
