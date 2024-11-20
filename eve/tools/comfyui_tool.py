import modal
from pydantic import BaseModel, Field
from typing import List, Optional, Dict

from ..tool import Tool
from ..task import Task


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
    comfyui_output_node_id: int
    comfyui_intermediate_outputs: Optional[Dict[str, int]] = None
    comfyui_map: Dict[str, ComfyUIInfo] = Field(default_factory=dict)

    @classmethod
    def _create_tool(cls, key: str, schema: dict, test_args: dict, **kwargs):
        """Create a new tool instance from a schema"""

        tool = super()._create_tool(key, schema, test_args, **kwargs)

        for field, props in schema.get('parameters', {}).items():
            if 'comfyui' in props:
                tool.comfyui_map[field] = props['comfyui']

        return tool

    @Tool.handle_run
    async def async_run(self, args: Dict, db: str):
        cls = modal.Cls.lookup(f"comfyuiNEW-{self.workspace}", "ComfyUI")
        result = await cls().run.remote.aio(self.parent_tool or self.key, args, db)
        return result

    @Tool.handle_start_task
    async def async_start_task(self, task: Task):
        cls = modal.Cls.lookup(f"comfyuiNEW-{self.workspace}", "ComfyUI")
        job = await cls().run_task.spawn.aio(task)
        return job.object_id
        
    @Tool.handle_wait
    async def async_wait(self, task: Task):
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        await fc.get.aio()
        task.reload()
        return task.model_dump(include={"status", "error", "result"})
        
    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        await fc.cancel.aio()

