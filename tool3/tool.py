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
        # note, this should be updated from main
        if not self.cost_estimate:
            return 0
        cost_formula = re.sub(r'(\w+)\.length', r'len(\1)', self.cost_estimate) # js to py
        cost_estimate = eval(cost_formula, args)
        assert isinstance(cost_estimate, (int, float)), "Cost estimate not a number"
        return cost_estimate

    def prepare_args(self, args: dict):
        unrecognized_args = set(args.keys()) - set(self.base_model.__fields__.keys())
        if unrecognized_args:
            raise ValueError(f"Unrecognized arguments provided: {', '.join(unrecognized_args)}")

        prepared_args = {}
        for field, field_info in self.base_model.__fields__.items():
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
            error_str = get_human_readable_error(e.errors())
            raise ValueError(error_str)

        return prepared_args

    """

    run with Task / User
    run anon/system

    run and wait
    submit, wait

    """




    # def handle_submit(submit_function):
    #     async def wrapper(self, task: Task, *args, **kwargs):
    #         user = User.from_id(task.user, env=env)
    #         task.args = self.prepare_args(task.args)
    #         task.cost = self.calculate_cost(task.args.copy())
    #         user.verify_manna_balance(task.cost)
    #         task.status = "pending"
    #         task.save()
    #         handler_id = await submit_function(self, task, *args, **kwargs)
    #         task.update({"handler_id": handler_id})
    #         user.spend_manna(task.cost)
    #         return handler_id
    #     return wrapper

    # def handle_submit(submit_function):
    #     async def wrapper(self, args: Dict, user_id: str, env: str):
    #         user = User.from_id(user_id)
    #         args = self.prepare_args(args)
    #         cost = self.calculate_cost(args.copy())
    #         user.verify_manna_balance(cost)
    #         task = Task(
    #             env=env,
    #             workflow=self.name,
    #             output_type=self.output_type, 
    #             args=args,
    #             user=ObjectId(user_id),
    #             cost=cost,
    #             status="pending"
    #         )
    #         task.save()
    #         handler_id = await submit_function(self, task)
    #         task.update({"handler_id": handler_id})
    #         user.spend_manna(task.cost)            
    #         return handler_id
    #     return wrapper



    def handle_run(run_function):
        async def wrapper(self, args: Dict, *args_, **kwargs):
            args = self.prepare_args(args)
            result = await run_function(self, args, *args_, **kwargs)
            # return self.get_user_result(result)
            return result
        return wrapper

    def handle_cancel(cancel_function):
        async def wrapper(self, task: Task):
            await cancel_function(self, task)
            n_samples = task.args.get("n_samples", 1)
            refund_amount = (task.cost or 0) * (n_samples - len(task.result)) / n_samples
            user = User.from_id(task.user, env=env)
            user.refund_manna(refund_amount)
            task.status = "cancelled"
            task.save()
        return wrapper

    # async def async_submit_and_run(self, task: Task):
    #     await self.async_submit(task)
    #     result = await self.async_process(task)
    #     return result 
    
    def run(self, args: Dict):
        return asyncio.run(self.async_run(args))

    def submit(self, task: Task):
        return asyncio.run(self.async_submit(task))

    def submit_and_run(self, task: Task):
        return asyncio.run(self.async_submit_and_run(task))
    
    def cancel(self, task: Task):
        return asyncio.run(self.async_cancel(task))





    







def get_human_readable_error(error_list):
    errors = [f"{error['loc'][0]}: {error['msg']}" for error in error_list]
    error_str = "\n\t".join(errors)
    error_str = f"Invalid args\n\t{error_str}"
    return error_str



# from comfyui_tool import ComfyUITool
# def load_comfyui_tool(tool_path: str, name: str = None) -> ComfyUITool:
#     tool = ComfyUITool.from_dir(tool_path, handler="comfyui")
#     return tool
