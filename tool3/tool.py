import os
import re
import yaml
import json
import random
import asyncio
import eden_utils
from pydantic import BaseModel, Field, create_model, ValidationError
from typing import Optional, List, Dict, Any, Type, Literal

import s3
from base import parse_schema
from models import Task, User


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
    handler: Literal["modal", "comfyui", "replicate", "gcp"] = "modal"
    base_model: Type[BaseModel] = Field(None, exclude=True)

    @classmethod
    def from_dir(cls, tool_dir: str, **kwargs):
        key = tool_dir.split('/')[-1]
        yaml_file = os.path.join(tool_dir, 'api.yaml')
        test_file = os.path.join(tool_dir, 'test.json')

        with open(yaml_file, 'r') as f:
            schema = yaml.safe_load(f)
                
        with open(test_file, 'r') as f:
            test_args = json.load(f)

        fields = parse_schema(schema)
        base_model = create_model(key, **fields)
        base_model.__doc__ = eden_utils.concat_sentences(schema.get('description'), schema.get('tip', ''))

        tool_data = {k: schema.pop(k) for k in cls.model_fields.keys() if k in schema}
        tool_data['test_args'] = test_args
        tool_data['base_model'] = base_model
        
        if 'cost_estimate' in tool_data:
            tool_data['cost_estimate'] = str(tool_data['cost_estimate'])

        return cls(key=key, **tool_data, **kwargs)

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

    def prepare_result(self, result, env: str):
        print("pr1")
        print(result)
        print(type(result))
        if isinstance(result, list):
            print("pr2")
            print(result)
            return [self.prepare_result(r, env=env) for r in result]
        elif isinstance(result, dict):
            print("pr3")
            print(result)
            return {k: self.prepare_result(v, env=env) for k, v in result.items()}
        elif type(result) in [str, int, float]:
            print("pr4")
            return result
        print("pr4")
        if "filename" in result:
            print("pr5")
            filename = result.pop("filename")
            print("pr6")
            result["url"] = f"{s3.get_root_url(env=env)}/{filename}"
            print("pr7")
        if "thumbnail" in result:
            print("pr8")
            result["thumbnail"] = self.prepare_result(result["thumbnail"], env=env)
            print("pr9")
        print("pr10")
        if "model" in result:
            print("pr11")
            result["model"] = str(result["model"])
            print("pr12")
            result.pop("metadata")  # don't need to return model metadata here since it's already in the task args
        if "intermediate_outputs" in result:
            print("pr12")
            result["intermediate_outputs"] = {
                k: self.prepare_result(v, env=env)
                for k, v in result["intermediate_outputs"].items()
            }
            print("pr13")
        print("THE RESU")
        print("GO!!! 11")
        print("the type is")
        print(type(result))
        print(result)
        print("GO!!!  22 ")
        return result

    def handle_run(run_function):
        async def wrapper(self, args: Dict, env: str):
            try:
                print("OR 0")
                args = self.prepare_args(args)
                print("OR 0-")
                result = await run_function(self, args, env)
                print("OR 1")
            except Exception as e:
                print("OR 2")
                result = {"error": str(e)}
                print("OR 3")
            print("OR 4")
            print(result)
            y= self.prepare_result(result, env)
            print("OR 5")
            print(y)
            print(result)
            print("OR 6")
            return y
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
                print("OR 5")
                print(e)
                task.update(status="failed", error=str(e))
                raise e
            return self.prepare_result(result, task.env)
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


def load_tool(tool_dir: str, **kwargs) -> Tool:
    """Load the tool class based on the handler in api.yaml"""
    
    from comfyui_tool import ComfyUITool
    from replicate_tool import ReplicateTool
    from modal_tool import ModalTool
    from gcp_tool import GCPTool
    from local_tool import LocalTool
    api_file = os.path.join(tool_dir, 'api.yaml')
    with open(api_file, 'r') as f:
        schema = yaml.safe_load(f)

    handler = schema.get('handler')
    handler_map = {
        "comfyui": ComfyUITool,
        "replicate": ReplicateTool,
        "modal": LocalTool,
        "gcp": GCPTool,
        None: LocalTool
    }
    
    tool_class = handler_map.get(handler, Tool)
    
    return tool_class.from_dir(tool_dir, **kwargs)


def get_tools(path: str, include_inactive: bool = False) -> Dict[str, Tool]:
    """Get all tools inside a directory"""
    
    tools = {}
    
    for root, _, files in os.walk(path):
        if "api.yaml" in files and "test.json" in files:
            rel_path = os.path.relpath(root, path)
            tool_name = rel_path.replace(os.path.sep, "/")  # Normalize path separator
            tool = load_tool(root)
            if tool.status != "inactive" and not include_inactive:
                tool_key = tool_name.split("/")[-1]
                if tool_key in tools:
                    raise ValueError(f"Duplicate tool {tool_key} found.")
                tools[tool_key] = tool
            
    return tools




def prepare_result(result, env: str):
    print("pr1")
    print(result)
    if isinstance(result, list):
        print("pr2")
        print(result)
        return [prepare_result(r, env=env) for r in result]
    elif isinstance(result, dict):
        print("pr3")
        print(result)
        return {k: prepare_result(v, env=env) for k, v in result.items()}
    elif type(result) in [str, int, float]:
        print("pr4")
        return result
    print("pr4")
    if "filename" in result:
        print("pr5")
        filename = result.pop("filename")
        print("pr6")
        result["url"] = f"{s3.get_root_url(env=env)}/{filename}"
        print("pr7")
    if "thumbnail" in result:
        print("pr8")
        result["thumbnail"] = prepare_result(result["thumbnail"], env=env)
        print("pr9")
    print("pr10")
    if "model" in result:
        print("pr11")
        result["model"] = str(result["model"])
        print("pr12")
        result.pop("metadata")  # don't need to return model metadata here since it's already in the task args
    if "intermediate_outputs" in result:
        print("pr12")
        result["intermediate_outputs"] = {
            k: prepare_result(v, env=env)
            for k, v in result["intermediate_outputs"].items()
        }
        print("pr13")
    print("THE RESU")
    print("GO!!! 11")
    print("the type is")
    print(type(result))
    print(result)
    print("GO!!!  22 ")
    return result