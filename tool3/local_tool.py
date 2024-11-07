import uuid
import modal
from typing import Dict
import asyncio

from models import Task, task_handler_func, task_handler_method
from tools import handlers
from tool import Tool
import eden_utils


class LocalTool(Tool):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tasks = {}

    @Tool.handle_run
    async def async_run(self, args: Dict, env: str):
        result = await handlers[self.key](args, env=env)
        return eden_utils.upload_result(result, env=env)

    @Tool.handle_start_task
    async def async_start_task(self, task: Task):
        task_id = str(uuid.uuid4())
        background_task = asyncio.create_task(run_task(task))
        self._tasks[task_id] = background_task
        return task_id
    
    @Tool.handle_wait
    async def async_wait(self, task: Task):
        if task.handler_id not in self._tasks:
            raise ValueError(f"No task found with id {task.handler_id}")            
        try:
            result = await self._tasks[task.handler_id]
            del self._tasks[task.handler_id]
            return result
        except asyncio.CancelledError:
            return {"status": "cancelled"}
    
    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        if task.handler_id in self._tasks:
            background_task = self._tasks[task.handler_id]
            background_task.cancel()
            try:
                await background_task
            except asyncio.CancelledError:
                pass
            finally:
                del self._tasks[task.handler_id]
        

@task_handler_func
async def run_task(tool_key: str, args: dict, env: str):
    return await handlers[tool_key](args, env=env)