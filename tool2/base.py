import random
import asyncio        
import re
import json
import os
import sys
import modal
sys.path.append('..')

import yaml
from pydantic import BaseModel, Field, create_model, ValidationError
from typing import Optional, List, Dict, Any, Union
from typing import List, Dict, Any, Union
from enum import Enum
from instructor.function_calls import openai_schema
from typing import Optional
from tool import ParameterType
from pydantic.json_schema import SkipJsonSchema


from tool import SkipJsonSchema
from typing import Optional, List, Type
from pydantic import BaseModel, Field
from tool import ParameterType, get_human_readable_error
from models import Task, User

import eden_utils

env = "STAGE"


def get_type(type_str: str):
    type_mapping = {
        'str': str,
        'int': int,
        'float': float,
        'bool': bool,
        'array': List,
        'object': Dict[str, Any]
    }
    return type_mapping.get(type_str, Any)

def create_enum(name: str, choices: List[str]):
    return Enum(name, {choice: choice for choice in choices})

def parse_schema(schema: dict):
    fields = {}
    required_fields = schema.get('required', [])
    for field, props in schema.get('properties', {}).items():
        field_kwargs = {}
        
        if 'description' in props:
            field_kwargs['description'] = props['description']
            if 'tip' in props:
                field_kwargs['description'] = eden_utils.concat_sentences(field_kwargs['description'], props['tip'])
        if 'example' in props:
            field_kwargs['example'] = props['example']
        if 'default' in props:
            field_kwargs['default'] = props['default']
        
        # Store additional properties
        additional_props = {'required': field in required_fields}
        if 'label' in props:
            additional_props['label'] = props['label']
        
        # Handle min and max for int and float
        if props['type'] in ['int', 'float']:
            if 'minimum' in props:
                field_kwargs['ge'] = props['minimum']
            if 'maximum' in props:
                field_kwargs['le'] = props['maximum']
        
        # Handle enum for strings
        if props['type'] == 'str' and 'enum' in props:
            enum_type = create_enum(f"{field.capitalize()}Enum", props['enum'])
            fields[field] = (enum_type, Field(**field_kwargs, **additional_props))
            continue
        
        if props['type'] == 'object':
            nested_model = create_model(field, **parse_schema(props))
            fields[field] = (nested_model, Field(**field_kwargs, **additional_props))
        elif props['type'] == 'array':
            item_type = get_type(props['items']['type'])
            if props['items']['type'] == 'object':
                item_type = create_model(f"{field}Item", **parse_schema(props['items']))
            fields[field] = (List[item_type], Field(**field_kwargs, **additional_props))
        else:
            fields[field] = (get_type(props['type']), Field(**field_kwargs, **additional_props))
    
        if not additional_props['required']:
            fields[field] = (Optional[fields[field][0]], fields[field][1])
            fields[field][1].default = field_kwargs.get("default", None)#or None #  fields[field][1].default or None

    return fields




class Tool(BaseModel):
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
        yaml_file = os.path.join(tool_dir, 'api.yaml')
        test_file = os.path.join(tool_dir, 'test.json')

        with open(yaml_file, 'r') as f:
            schema = yaml.safe_load(f)
        
        with open(test_file, 'r') as f:
            test_args = json.load(f)

        fields = parse_schema(schema)
        base_model = create_model(schema['name'], **fields)
        base_model.__doc__ = eden_utils.concat_sentences(schema.get('description'), schema.get('tip', ''))

        # Extract known fields
        tool_data = {k: schema.pop(k) for k in cls.__fields__.keys() if k in schema}
        tool_data['test_args'] = test_args
        tool_data['base_model'] = base_model

        return cls(**tool_data, **kwargs)

    def calculate_cost(self, args):
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

    def handle_run(run_function):
        async def wrapper(self, args: Dict, *args_, **kwargs):
            args = self.prepare_args(args)
            result = await run_function(self, args, *args_, **kwargs)
            return self.get_user_result(result)
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

class ComfyUITool(Tool):
    workspace: str
    comfyui_output_node: int
    comfyui_intermediate_outputs: Optional[Dict[str, int]] = None
    comfyui_map: Dict[str, ComfyUIInfo] = Field(default_factory=dict)

    @classmethod
    def from_dir(cls, tool_dir: str):
        workspace = "myworkspace" # tool_dir.split('/')[-2]
        tool = super().from_dir(tool_dir, workspace=workspace)

        yaml_file = os.path.join(tool_dir, 'api.yaml')
        with open(yaml_file, 'r') as f:
            schema = yaml.safe_load(f)

        for field, props in schema.get('properties', {}).items():
            if 'comfyui' in props:
                tool.comfyui_map[field] = props['comfyui']

        return tool
    
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


"""
submit
- pass back handler id
- runner function (actual processing)

Modal
 - runner = pass (on Modal)
ComfyUI
 - runner = pass (on ComfyUI)
Replicate

"""    



# Usage:
#comfy_tool = Tool.from_dir('person')
comfy_tool = ComfyUITool.from_dir('person')

# print(regular_tool)
print(comfy_tool)
print(comfy_tool.comfyui_map)

print(comfy_tool.base_model.__fields__['age'])


args = comfy_tool.prepare_args({
    'name': 'John', 
    # 'age': 30, 
    'height': 1.75,
    # "blah": "3452"
})

print("-======")
print(args)





# Example usage
# person_instance = PersonModel(
#     name="John",
#     age=30,
#     height=1.75,
#     hobbies=["swimming", "reading", "coding"],
#     contacts=[
#         {"type": "email", "value": "john@example.com"},
#         {"type": "phone", "value": "123456789"}
#     ],
#     address={"street": "123 Main St", "city": "Somewhere", "postal_code": 12345},
#     matrix={"data": [[1, 2, 3], [4, 5, 6], [7, 8, 9]]}
# )









test_api_data = """
name: "Person"
description: "This model represents a person with their details like name, age, hobbies, contacts, and address."
tip: "Person is a model that represents a person and stuff."
cost_estimate: "50"
comfyui_output_node: 161
comfyui_intermediate_outputs:
  controlnet_signal: 323
properties:
  name:
    type: "str"
    description: "The person's name"
    example: "John"
    label: "Full Name"
    required: true
    enum: ["John", "Jane", "Alice", "Bob"]
  age:
    type: "int"
    description: "The person's age"
    example: 30
    label: "Age"
    default: random
    minimum: 0
    maximum: 120
    comfyui:
      node_id: 162
      field: height
      subfield: height
  height:
    type: "float"
    description: "The person's height in meters"
    example: 1.75
    minimum: 0.5
    maximum: 2.5
    tip: "Height is measured in meters"
  hobbies:
    type: "array"
    items:
      type: "str"
    description: "List of hobbies"
    default: ["reading", "swimming", "coding"]
    example: ["reading", "swimming", "coding"]
  contacts:
    type: "array"
    items:
      type: object
      properties:
        type:
          type: "str"
          description: "The contact method type"
          example: "email"
          enum: ["email", "phone", "social_media"]
        value:
          type: "str"
          description: "The contact value"
          example: "john@example.com"
    description: "A list of contact methods"
    example: [{"type": "email", "value": "john@example.com"}, {"type": "phone", "value": "123456789"}]
  address:
    type: object
    properties:
      street:
        type: "str"
        description: "The street address"
        example: "123 Main St"
      city:
        type: "str"
        description: "The city name"
        example: "Somewhere"
      postal_code:
        type: "int"
        description: "Postal code for the address"
        example: 12345
        minimum: 10000
        maximum: 99999
    description: "The person's address"
    example: {"street": "123 Main St", "city": "Somewhere", "postal_code": 12345}
  matrix:
    type: object
    properties:
      data:
        type: "array"
        items:
          type: "array"
          items:
            type: "int"
        description: "A row in the matrix"
    description: "A 2D array of integers (matrix)"
    tip: "Matrix is a 2D array of integers"
    example: {"data": [[1, 2, 3], [4, 5, 6], [7, 8, 9]]}
"""



