import modal
from typing import Dict

from ..task import Task, task_handler_func
from ..tools import handlers
from ..tool import Tool
from .. import eden_utils


class ModalTool(Tool):
    @Tool.handle_run
    async def async_run(self, args: Dict, env: str):
        func = modal.Function.lookup("handlers2", "run")
        result = await func.remote.aio(tool_key=self.parent_tool or self.key, args=args, env=env)
        return result

    @Tool.handle_start_task
    async def async_start_task(self, task: Task):
        func = modal.Function.lookup("handlers2", "run_task")
        job = func.spawn(task, parent_tool=self.parent_tool)
        return job.object_id
    
    @Tool.handle_wait
    async def async_wait(self, task: Task):
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        await fc.get.aio()
        task.reload()
        return task.result
    
    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        await fc.cancel.aio()


