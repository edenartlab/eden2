import os
import re
import copy
import click
import yaml
import copy
import json
import random
import asyncio
import eden_utils
from pprint import pprint
from pydantic import BaseModel, Field, create_model, ValidationError
from typing import Optional, List, Dict, Any, Type, Literal
import datetime

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
    parameter_presets: Optional[Dict[str, Any]] = None

    # @classmethod
    # def get_collection_name(cls) -> str:
    #     return "tools2"

    @classmethod
    def load_from_dir(cls, tool_dir: str, **kwargs):
        """Load the tool class from a directory api.yaml and test.json"""

        key = tool_dir.split('/')[-1]
        schema, test_args = cls._get_schema_from_dir(tool_dir)
        tool_class = _get_tool_class(schema.get('handler'))

        return tool_class._create_tool(key, schema, test_args, **kwargs)

    @classmethod
    def load(cls, key: str, env: str, prefer_local: bool = True, **kwargs):
        """Load the tool class based on the handler in api.yaml"""
        
        tools = get_collection("tools2", env=env)
        schema = tools.find_one({"key": key})
        key = schema.pop('key')
        test_args = schema.pop('test_args')

        tool_class = _get_tool_class(schema.get('handler'), prefer_local)
        return tool_class._create_tool(key, schema, test_args, **kwargs)    

    @classmethod
    def _create_tool(cls, key: str, schema: dict, test_args: dict, **kwargs):
        """Create a new tool instance from a schema"""

        fields = parse_schema(schema)
        base_model = create_model(key, **fields)
        base_model.__doc__ = eden_utils.concat_sentences(schema.get('description'), schema.get('tip', ''))

        tool_data = {k: schema.pop(k) for k in cls.model_fields.keys() if k in schema}
        tool_data['test_args'] = test_args
        tool_data['base_model'] = base_model
        if 'cost_estimate' in tool_data:
            tool_data['cost_estimate'] = str(tool_data['cost_estimate'])

        return cls(key=key, **tool_data, **kwargs)

    @classmethod
    def _get_schema_from_dir(cls, tool_dir: str, **kwargs):
        api_file = os.path.join(tool_dir, 'api.yaml')
        test_file = os.path.join(tool_dir, 'test.json')

        with open(api_file, 'r') as f:
            schema = yaml.safe_load(f)
                
        with open(test_file, 'r') as f:
            test_args = json.load(f)

        if schema.get("handler") == "comfyui":
            schema["workspace"] = tool_dir.split('/')[-3]

        parent_tool = schema.get("parent_tool")
        
        if parent_tool:
            tool_dirs = get_tool_dirs()
            if schema["parent_tool"] not in tool_dirs:
                raise ValueError(f"Parent tool {schema['parent_tool']} not found in tool_dirs")            
            parent_dir = tool_dirs[schema["parent_tool"]]
            parent_api_file = os.path.join(parent_dir, 'api.yaml')
            with open(parent_api_file, 'r') as f:
                parent_schema = yaml.safe_load(f)

            if parent_schema.get("handler") == "comfyui":
                parent_schema["workspace"] = parent_dir.split('/')[-3]

            parent_schema["parameter_presets"] = schema.pop("parameters", {})
            parent_parameters = parent_schema.pop("parameters", {})
            for k, v in parent_schema["parameter_presets"].items():
                parent_parameters[k].update(v)
            
            parent_schema.update(schema)
            parent_schema['parameters'] = parent_parameters
            schema = parent_schema
        
        return schema, test_args

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
            
            # create task and set to pending
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
    

def save_tool_from_dir(tool_dir: str, env: str) -> Tool:
    """Upload tool from directory to mongo"""

    schema, test_args = Tool._get_schema_from_dir(tool_dir)
    schema['key'] = tool_dir.split('/')[-1]
    schema['test_args'] = test_args
    
    tools = get_collection("tools2", env=env)
    tool = tools.find_one({"key": schema['key']})
    
    time = datetime.datetime.utcnow()
    schema['createdAt'] = tool.get('createdAt', time) if tool else time
    schema['updatedAt'] = time
    
    tools.replace_one({"key": schema['key']}, schema, upsert=True)


# def save_tools(tools: List[str] = None, env: str = "STAGE") -> Dict[str, Tool]:
#     """Get all tools inside a directory and upload to mongo"""
    
#     tool_dirs = get_tool_dirs()
    
#     for key, tool_dir in tool_dirs.items():
#         if tools and key not in tools:
#             continue
#         save_tool_from_dir(tool_dir, env=env)
        
#     return tools


def get_tools_from_dirs(root_dir: str = None, include_inactive: bool = False) -> Dict[str, Tool]:
    """Get all tools inside a directory"""
    
    tool_dirs = get_tool_dirs(root_dir)
    tools = {
        key: Tool.load_from_dir(tool_dir, include_inactive=include_inactive) 
        for key, tool_dir in tool_dirs.items()
    }

    return tools


def get_tools_from_mongo(env: str, include_inactive: bool = False) -> Dict[str, Tool]:
    """Get all tools from mongo"""
    
    tools = {}
    tools_collection = get_collection("tools2", env=env)
    for tool in tools_collection.find():
        tool = Tool.load(tool['key'], env=env)
        if tool.status != "inactive" and not include_inactive:
            if tool.key in tools:
                raise ValueError(f"Duplicate tool {tool.key} found.")
            tools[tool.key] = tool
        
    return tools


def get_tool_dirs(root_dir: str = None, include_inactive: bool = False) -> List[str]:
    """Get all tool directories inside a directory"""
    
    tool_dirs = {}
    root_dirs = [root_dir] if root_dir else ["tools", "../../workflows"]
    
    for root_dir in root_dirs:
        for root, _, files in os.walk(root_dir):
            if "api.yaml" in files and "test.json" in files:
                api_file = os.path.join(root, "api.yaml")
                with open(api_file, 'r') as f:
                    schema = yaml.safe_load(f)
                if schema.get("status") == "inactive" and not include_inactive:
                    continue
                key = os.path.relpath(root).split("/")[-1]
                if key in tool_dirs:
                    raise ValueError(f"Duplicate tool {key} found.")
                tool_dirs[key] = os.path.relpath(root)
            
    return tool_dirs


def _get_tool_class(handler: str, prefer_local: bool = True):
    from comfyui_tool import ComfyUITool
    from replicate_tool import ReplicateTool
    from modal_tool import ModalTool
    from gcp_tool import GCPTool
    from local_tool import LocalTool

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
    

@click.group()
def cli():
    """Tool management CLI"""
    pass

@cli.command()
@click.option('--env', type=click.Choice(['STAGE', 'PROD']), default='STAGE', help='DB to save against')
@click.argument('tools', nargs=-1, required=False)
def update(env: str, tools: tuple):
    """Update tools in mongo"""
    
    tool_dirs = get_tool_dirs()
    
    if tools:
        tool_dirs = {k: v for k, v in tool_dirs.items() if k in tools}
    else:
        confirm = click.confirm(f"Update all {len(tool_dirs)} tools on {env}?", default=False)
        if not confirm:
            return

    for key, tool_dir in tool_dirs.items():
        try:
            save_tool_from_dir(tool_dir, env=env)
            click.echo(click.style(f"Updated {env}:{key}", fg='green'))
        except Exception as e:
            click.echo(click.style(f"Failed to update {env}:{key}: {e}", fg='red'))

    click.echo(click.style(f"\nUpdated {len(tool_dirs)} tools", fg='blue', bold=True))


@cli.command()
@click.option('--from_dirs', default=True, help='Whether to load tools from folders (default is from mongo)')
@click.option('--env', type=click.Choice(['STAGE', 'PROD']), default='STAGE', help='DB to load tools from if from mongo')
@click.option('--api', is_flag=True, help='Run tasks against API (If not set, will run tools directly)')
@click.option('--parallel', is_flag=True, default=True, help='Run tests in parallel threads')
@click.option('--save', is_flag=True, default=True, help='Save test results')
@click.argument('tools', nargs=-1, required=False)
def test(
    tools: tuple,
    from_dirs: bool, 
    env: str, 
    api: bool, 
    parallel: bool, 
    save: bool
):
    """Run tools with test args"""

    from test_tools2 import save_test_results

    async def async_test_tool(tool, api, env):
        color = random.choice(["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white", "bright_black", "bright_red", "bright_green", "bright_yellow", "bright_blue", "bright_magenta", "bright_cyan", "bright_white"])
        click.echo(click.style(f"\n\nTesting {tool.key}:", fg=color, bold=True))
        click.echo(click.style(f"Args: {json.dumps(tool.test_args, indent=2)}", fg=color))

        if api:
            user_id = os.getenv("EDEN_TEST_USER_STAGE")
            task = await tool.async_start_task(user_id, tool.test_args, env=env)
            result = await tool.async_wait(task)
        else:
            result = await tool.async_run(tool.test_args, env=env)
        
        if "error" in result:
            click.echo(click.style(f"Failed to test {tool.key}: {result['error']}", fg='red', bold=True))
        else:
            click.echo(click.style(f"Result: {json.dumps(result, indent=2)}", fg=color))

        return result

    async def async_run_tests(tools, api, env, parallel):
        tasks = [async_test_tool(tool, api, env) for tool in tools.values()]
        if parallel:
            results = await asyncio.gather(*tasks)
        else:
            results = [await task for task in tasks]
        return results

    if from_dirs:
        all_tools = get_tools_from_dirs()
    else:
        all_tools = get_tools_from_mongo(env=env)

    if tools:
        tools = {k: v for k, v in all_tools.items() if k in tools}
    else:
        tools = all_tools
        confirm = click.confirm(f"Run tests for all {len(tools)} tools?", default=False)
        if not confirm:
            return

    results = asyncio.run(async_run_tests(tools, api, env, parallel))
    if save:
        save_test_results(tools, results)

    errors = [result for result in results if "error" in result]
    click.echo(click.style(f"\n\nTested {len(tools)} tools with {len(errors)} errors: {', '.join(errors)}", fg='blue', bold=True))


if __name__ == '__main__':
    cli()
