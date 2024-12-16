from bson import ObjectId
from typing import Dict, Any, Optional, Literal, List
from functools import wraps
from datetime import datetime, timezone
import asyncio

from .user import User
from .mongo import Document, Collection
from . import eden_utils



@Collection("creations3")
class Creation(Document):
    user: ObjectId
    requester: ObjectId
    task: ObjectId
    tool: str
    filename: str
    mediaAttributes: Optional[Dict[str, Any]] = None
    name: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    public: bool = False
    deleted: bool = False

    def __init__(self, **data):
        if isinstance(data.get('user'), str):
            data['user'] = ObjectId(data['user'])
        if isinstance(data.get('requesteder'), str):
            data['requester'] = ObjectId(data['requester'])
        if isinstance(data.get('task'), str):
            data['task'] = ObjectId(data['task'])
        super().__init__(**data)


@Collection("tasks3")
class Task(Document):
    user: ObjectId
    requester: ObjectId
    tool: str
    parent_tool: Optional[str] = None
    output_type: str
    args: Dict[str, Any]
    mock: bool = False
    cost: float = None
    handler_id: Optional[str] = None
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = "pending"
    error: Optional[str] = None
    result: Optional[List[Dict[str, Any]]] = None
    performance: Optional[Dict[str, Any]] = {}

    def __init__(self, **data):
        if isinstance(data.get('user'), str):
            data['user'] = ObjectId(data['user'])
        if isinstance(data.get('requester'), str):
            data['requester'] = ObjectId(data['requester'])
        super().__init__(**data)

    @classmethod
    def from_handler_id(self, handler_id: str, db: str):
        tasks = self.get_collection(db)
        task = tasks.find_one({"handler_id": handler_id})
        if not task:
            raise Exception("Task not found")    
        return super().load(self, task["_id"], db)


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


async def _preprocess_task(task: Task):
    """Helper function that sleeps for 5 seconds"""
    await asyncio.sleep(5)
    return {"name": "this is a tbd side task"}


async def _task_handler(func, *args, **kwargs):
    print(" == TH 1")
    task = kwargs.pop("task", args[-1])
    
    start_time = datetime.now(timezone.utc)
    queue_time = (start_time - task.createdAt).total_seconds()

    print(" == TH 2")
    task.update(
        status="running",
        performance={"waitTime": queue_time}
    )
    print(" == TH 3")

    results = []
    n_samples = task.args.get("n_samples", 1)
    print(" == TH 4")
    try:
        for i in range(n_samples):
            print(" == TH 5, i", i)
            task_args = task.args.copy()
            if "seed" in task_args:
                task_args["seed"] = task_args["seed"] + i

            # Run both functions concurrently
            main_task = func(*args[:-1], task.parent_tool or task.tool, task_args, task.db)
            preprocess_task = _preprocess_task(task)
            print(" == TH 6")
            result, preprocess_result = await asyncio.gather(main_task, preprocess_task)
            print(" == TH 7")
            print(result)
            print(" == TH 8")
            
            result["output"] = result["output"] if isinstance(result["output"], list) else [result["output"]]
            print(" == TH 9")
            result = eden_utils.upload_result(result, db=task.db, save_thumbnails=True, save_blurhash=True)
            print(" == TH 10")
            print(result)

            for output in result["output"]:
                print(" == TH 11")
                name = preprocess_result.get("name") or task_args.get("prompt") or args.get("text_input")
                if not name:
                    name = args.get("interpolation_prompts") or args.get("interpolation_texts")
                    if name:
                        name = " to ".join(name)
                print(" == TH 12")
                new_creation = Creation(
                    user=task.user,
                    requester=task.requester,
                    agent=None,
                    task=task.id,
                    tool=task.tool,
                    filename=output['filename'],
                    mediaAttributes=output['mediaAttributes'],
                    name=name
                )
                new_creation.save(db=task.db)
                output["creation"] = new_creation.id
                print(" == TH 13")
                print(output)

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

            print(" == TH 14")
            print(task_update)

        return task_update.copy()

    except Exception as error:
        print(" == TH 15 ERRR")
        print(error)
        task_update = {
            "status": "failed",
            "error": str(error),
        }
        
        n_samples = task.args.get("n_samples", 1)
        refund_amount = (task.cost or 0) * (n_samples - len(task.result or [])) / n_samples
        user = User.load(task.user, db=task.db)
        user.refund_manna(refund_amount)
        print(" == TH 16")
        
        return task_update.copy()

    finally:
        print(" == TH 17")
        run_time = datetime.now(timezone.utc) - start_time
        task_update["performance"] = {
            "waitTime": queue_time,
            "runTime": run_time.total_seconds()
        }
        print(" == TH 17.5")
        print(task_update)
        task.update(**task_update)
        print(" == TH 18")