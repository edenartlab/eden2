from bson import ObjectId
from typing import Dict, Any, Optional, Literal
from functools import wraps
from datetime import datetime

from .models import User
from .mongo import MongoModel, get_collection
from . import eden_utils



class Task(MongoModel):
    workflow: str
    parent_tool: Optional[str] = None
    output_type: str
    args: Dict[str, Any]
    mock: bool = False
    user: ObjectId
    handler_id: Optional[str] = None
    cost: float = None
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = "pending"
    error: Optional[str] = None
    result: Optional[Any] = None
    performance: Optional[Dict[str, Any]] = {}

    def __init__(self, env, **data):
        if isinstance(data.get('user'), str):
            data['user'] = ObjectId(data['user'])
        super().__init__(env=env, **data)

    @classmethod
    def get_collection_name(cls) -> str:
        return "tasks2"

    @classmethod
    def from_handler_id(self, handler_id: str, env: str):
        tasks = get_collection(self.get_collection_name(), env=env)
        task = tasks.find_one({"handler_id": handler_id})
        if not task:
            raise Exception("Task not found")    
        return super().load(self, task["_id"], "tasks2", env)


def task_handler_func(func):
    @wraps(func)
    async def wrapper(task: Task):
        return await _task_handler(func, task)
    return wrapper


def task_handler_method(func):
    @wraps(func)
    async def wrapper(self, task: Task):
        return await _task_handler(func, self, task)
    return wrapper


async def _task_handler(func, *args, **kwargs):
    task = kwargs.pop("task", args[-1])
    
    start_time = datetime.utcnow()
    queue_time = (start_time - task.createdAt).total_seconds()
    #boot_time = queue_time - self.launch_time if self.launch_time else 0

    # print(task)
    task.update(
        status="running",
        performance={"waitTime": queue_time}
    )

    results = []
    n_samples = task.args.get("n_samples", 1)
    
    try:
        for i in range(n_samples):
            task_args = task.args.copy()
            if "seed" in task_args:
                task_args["seed"] = task_args["seed"] + i

            result = await func(*args[:-1], task.parent_tool or task.workflow, task_args, task.env)
            result = eden_utils.upload_result(result, env=task.env)
            results.extend([result])
            
            if i == n_samples - 1:
                task_update = {
                    "status": "completed", 
                    "result": results
                }
            else:
                task_update = {
                    "status": "running", 
                    "result": results
                }
                task.update(**task_update)

        return task_update.copy()

    except Exception as error:
        task_update = {
            "status": "failed",
            "error": str(error),
        }
        
        n_samples = task.args.get("n_samples", 1)
        refund_amount = (task.cost or 0) * (n_samples - len(task.result or [])) / n_samples
        user = User.load(task.user, env=task.env)
        user.refund_manna(refund_amount)
        
        # return task_update
        return task_update.copy()

    finally:
        run_time = datetime.utcnow() - start_time
        task_update["performance"] = {
            "waitTime": queue_time,
            "runTime": run_time.total_seconds()
        }
        task.update(**task_update)
        #self.launch_time = 0
