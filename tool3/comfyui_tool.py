# import sys
# sys.path.append('..')
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from pydantic import Field
import yaml
import modal
import os

from tool import Tool
from models import Task







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
        cls = modal.Cls.lookup(f"comfyuiNEW-{self.workspace}", "ComfyUI")
        result = await cls().run.remote.aio(self.key, args)
        return result

    # @Tool.handle_submit
    async def async_start_task(self, task: Task):
        cls = modal.Cls.lookup(f"comfyuiNEW-{self.workspace}", "ComfyUI")
        job = await cls().run_task.spawn.aio(task)
        return job.object_id
        
    
    async def async_wait(self, task: Task):
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












########################################################
########################################################



