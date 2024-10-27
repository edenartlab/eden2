# import sys
# sys.path.append('..')

from tool import Tool



from models import Task
from typing import Dict

import modal



"""

scenarios: 
- just run the tool (admin user, no manna) and WAIT
- run the tool with manna user and task and WAIT
- run the tool with manna (non-admin user)



"""





env = "STAGE"


class ModalTool(Tool):
    @Tool.handle_run
    async def async_run(self, args: Dict):
        func = modal.Function.lookup("handlers", "run")
        # result = await func.remote.aio(self.key, args)
        result = await func.remote.aio(tool_name="tool2", args=args)
        return result

    @Tool.handle_submit
    async def async_submit(self, task: Task):
        func = modal.Function.lookup("handlers", "submit")
        job = func.spawn(str(task.id), env=env)
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


