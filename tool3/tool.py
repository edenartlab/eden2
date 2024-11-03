"""
Todo:
- enforce choices on inner fields
e.g.
    'contacts': [
        {'type': 'emai3l', 'value': 'widget@hotmail.com'},
        {'type': 'phon3e', 'value': '555-1234'},
})

test remap
"""

import random
import re
import asyncio
import json
import os
import sys
sys.path.append('..')
import eden_utils

from bson import ObjectId
import yaml
from pydantic import BaseModel, Field, create_model, ValidationError
from typing import Optional, List, Dict, Any, Type

from base import parse_schema


from models import Task, User

from pprint import pprint
from functools import wraps
from datetime import datetime

class Tool(BaseModel):
    key: str
    name: str
    description: str
    tip: Optional[str] = None
    cost_estimate: str
    resolutions: Optional[List[str]] = None
    gpu: Optional[str] = "A100"
    private: Optional[bool] = False
    test_args: Dict[str, Any]
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
            elif field_info.default:
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
        async def wrapper(self, args: Dict, *args_, **kwargs):
            args = self.prepare_args(args)
            result = await run_function(self, args, *args_, **kwargs)
            # return self.get_user_result(result)
            return result
        return wrapper
    
    # task.update(handler_id=handler_id)

    def handle_cancel(cancel_function):
        async def wrapper(self, task: Task):
            await cancel_function(self, task)
            n_samples = task.args.get("n_samples", 1)
            refund_amount = (task.cost or 0) * (n_samples - len(task.result)) / n_samples
            user = User.from_id(task.user, env=task.env)
            user.refund_manna(refund_amount)
            task.status = "cancelled"
            task.save()
        return wrapper

    # async def async_submit_and_run(self, task: Task):
    #     await self.async_submit(task)
    #     result = await self.async_process(task)
    #     return result 

    async def async_run_task_and_wait(self, task: Task):
        await self.async_start_task(task, webhook=False)
        result = await self.async_wait(task)
        return result

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

    def run(self, args: Dict):
        return asyncio.run(self.async_run(args))

    def start_task(self, task: Task):
        return asyncio.run(self.async_start_task(task))

    def wait(self, task: Task):
        return asyncio.run(self.async_start_task_and_wait(task))

    def start_task_and_wait(self, task: Task):
        return asyncio.run(self.async_start_task_and_wait(task))
    
    def cancel(self, task: Task):
        return asyncio.run(self.async_cancel(task))




    










# from comfyui_tool import ComfyUITool
# def load_comfyui_tool(tool_path: str, name: str = None) -> ComfyUITool:
#     tool = ComfyUITool.from_dir(tool_path, handler="comfyui")
#     return tool



def get_tools(path: str):
    """Get all tools in a directory"""

    return {
        tool: load_tool(f"{path}/{tool}") 
            for tool in os.listdir(path) 
            if os.path.isdir(f"{path}/{tool}") and 
            os.path.exists(f"{path}/{tool}/api.yaml")
    }


def load_tool(tool_dir: str, **kwargs) -> Tool:
    """Load the tool class based on the handler in api.yaml"""
    
    from comfyui_tool import ComfyUITool
    from replicate_tool import ReplicateTool
    from modal_tool import ModalTool
    
    # Read the yaml file to check handler type
    yaml_file = os.path.join(tool_dir, 'api.yaml')
    with open(yaml_file, 'r') as f:
        schema = yaml.safe_load(f)
    
    # Get handler type from schema
    handler = schema.get('handler')
    
    # Map handlers to their respective tool classes
    handler_map = {
        "comfyui": ComfyUITool,
        "replicate": ReplicateTool,
        "modal": ModalTool,
        None: ModalTool
    }
    
    tool_class = handler_map.get(handler, Tool)
    return tool_class.from_dir(tool_dir, **kwargs)

