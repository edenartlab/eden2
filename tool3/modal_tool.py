# import sys
# sys.path.append('..')

from tool import Tool



from models import Task
from typing import Dict
from functools import wraps
import modal
from datetime import datetime


from models import Task, User


# def task_handler2(func):
#     @wraps(func)
#     async def wrapper(task_id: str, env: str):
#         task = Task.load(task_id, env=env)
#         print(task)
        
#         start_time = datetime.utcnow()
#         queue_time = (start_time - task.createdAt).total_seconds()
        
#         task.update(
#             status="running",
#             performance={"waitTime": queue_time}
#         )

#         try:
#             result = await func(task.workflow, task.args, task.user, env=env)
#             task_update = {
#                 "status": "completed", 
#                 "result": result
#             }
#             return task_update

#         except Exception as e:
#             print("Task failed", e)
#             task_update = {"status": "failed", "error": str(e)}
#             user = User.load(task.user, env=env)
#             user.refund_manna(task.cost or 0)

#         finally:
#             run_time = datetime.utcnow() - start_time
#             task_update["performance"] = {
#                 "waitTime": queue_time,
#                 "runTime": run_time.total_seconds()
#             }
#             task.update(**task_update)

#     return wrapper


# from pprint import pprint
# import eden_utils

# def task_handler(func):
#     @wraps(func)
#     async def wrapper(task_id: str, env: str):
#         task = Task.load(task_id, env=env)
#         print(task)
        
#         start_time = datetime.utcnow()
#         queue_time = (start_time - task.createdAt).total_seconds()
#         #boot_time = queue_time - self.launch_time if self.launch_time else 0
        
#         task.update(
#             status="running",
#             performance={"waitTime": queue_time}
#         )

#         result = []
#         n_samples = task.args.get("n_samples", 1)
#         pprint(task.args)
        
#         try:
#             for i in range(n_samples):
#                 args = task.args.copy()
#                 if "seed" in args:
#                     args["seed"] = args["seed"] + i

#                 output, intermediate_outputs = await func(task.workflow, args, env=env)
#                 print("intermediate_outputs", intermediate_outputs)

#                 result_ = eden_utils.upload_media(output, env=env)
#                 if intermediate_outputs:
#                     result_[0]["intermediateOutputs"] = {
#                         k: eden_utils.upload_media(v, env=env, save_thumbnails=False)
#                         for k, v in intermediate_outputs.items()
#                     }
                
#                 result.extend(result_)

#                 if i == n_samples - 1:
#                     task_update = {
#                         "status": "completed", 
#                         "result": result
#                     }
#                 else:
#                     task_update = {
#                         "status": "running", 
#                         "result": result
#                     }
#                     task.update(task_update)
    
#             return task_update

#         except Exception as e:
#             return task.catch_error(e)

#         finally:
#             run_time = datetime.utcnow() - start_time
#             task_update["performance"] = {
#                 "waitTime": queue_time,
#                 "runTime": run_time.total_seconds()
#             }
#             task.update(**task_update)
#             #self.launch_time = 0

#     return wrapper



class ModalTool(Tool):
    @Tool.handle_run
    async def async_run(self, args: Dict):
        func = modal.Function.lookup("handlers2", "run")
        # result = await func.remote.aio(self.key, args)
        result = await func.remote.aio(tool_name="tool2", args=args)
        return result

    # @Tool.handle_submit
    async def async_submit(self, task: Task):
        print("SUBMIT!")
        func = modal.Function.lookup("handlers2", "submit")
        job = func.spawn(str(task.id), env="STAGE")
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


