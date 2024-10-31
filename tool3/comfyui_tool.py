# import sys
# sys.path.append('..')
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from pydantic import Field
import yaml
import os

from tool import Tool
from models import Task

import modal





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
        workspace = tool_dir.split('/')[-3]
        tool = super().from_dir(tool_dir, workspace=workspace)

        yaml_file = os.path.join(tool_dir, 'api.yaml')
        with open(yaml_file, 'r') as f:
            schema = yaml.safe_load(f)

        for field, props in schema.get('parameters', {}).items():
            if 'comfyui' in props:
                tool.comfyui_map[field] = props['comfyui']

        return tool

    @Tool.handle_run
    async def async_run(self, args: Dict):
        func = modal.Function.lookup("handlers3", "run")
        result = await func.remote.aio(self.key, args)
        # result = await func.remote.aio(tool_name="tool2", args=args)
        return result

    # @Tool.handle_submit
    async def async_submit(self, task: Task):
        print("SUBMIT!")
        print(self.workspace)
        func = modal.Function.lookup("handlers3", "submit")
        env="STAGE"
        job = func.spawn(str(task.id), env=env)
        return job.object_id
        
    
    async def async_process(self, task: Task):
        if not task.handler_id:
            task.reload()
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        await fc.get.aio()
        task.reload()
        # return self.get_user_result(task.result)
        return task.result
    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        await fc.cancel.aio()


