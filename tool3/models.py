from bson import ObjectId
from typing import Dict, Any, Optional, List, Literal
from functools import wraps
from datetime import datetime
from pymongo.collection import Collection
from pydantic.json_schema import SkipJsonSchema
from pydantic import Field

from mongo import MongoModel, get_collection
import eden_utils


class Model(MongoModel):
    name: str
    user: ObjectId
    task: ObjectId
    slug: str = None
    thumbnail: str
    public: bool = False
    args: Dict[str, Any]
    checkpoint: str
    base_model: str
    # users: SkipJsonSchema[Optional[Collection]] = Field(None, exclude=True)

    # def __init__(self, env, **data):
    #     super().__init__(collection_name="models", env=env, **data)
    #     # self.users = get_collection("users", env=env)
    #     self._make_slug()

    def __init__(self, env, **data):
        if isinstance(data.get('user'), str):
            data['user'] = ObjectId(data['user'])
        if isinstance(data.get('task'), str):
            data['task'] = ObjectId(data['task'])
        super().__init__(env=env, **data)


    # @classmethod
    # def from_id(self, document_id: str, env: str):
    #     # self.users = get_collection("users", env=env)
    #     return super().from_id(self, document_id, "models", env)

    @classmethod
    def get_collection_name(cls) -> str:
        return "models"

    def _make_slug(self):
        # if self.collection is None:
        #     return
        if self.slug:
            # slug already assigned
            return
        name = self.name.lower().replace(" ", "-")
        collection = get_collection(self.get_collection_name(), env=self.env)
        existing_docs = list(collection.find({"name": self.name, "user": self.user}))
        versions = [int(doc.get('slug', '').split('/')[-1][1:]) for doc in existing_docs if doc.get('slug')]
        new_version = max(versions or [0]) + 1
        users = get_collection("users", env=self.env)
        username = users.find_one({"_id": self.user})["username"]
        # username = self.users.find_one({"_id": self.user})["username"]
        self.slug = f"{username}/{name}/v{new_version}"

    def save(self, upsert_query=None):
        self._make_slug()
        super().save(upsert_query)
    
    def update(self, **kwargs):
        self._make_slug()
        super().update(**kwargs)


class Task(MongoModel):
    workflow: str
    output_type: str
    args: Dict[str, Any]
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

    # def catch_error(self, error):
    #     print("Task failed", error)
    #     print("self", error)
    #     print("self", type(error))
    #     self.status = "error"
    #     self.error = str(error)
    #     self.save()
    #     n_samples = self.args.get("n_samples", 1)
    #     refund_amount = (self.cost or 0) * (n_samples - len(self.result)) / n_samples
    #     user = User.load(self.user, env=self.env)
    #     user.refund_manna(refund_amount)
    #     return {"status": "failed", "error": str(error)}






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
    parent_tool = kwargs.pop("parent_tool", None)
    
    start_time = datetime.utcnow()
    queue_time = (start_time - task.createdAt).total_seconds()
    #boot_time = queue_time - self.launch_time if self.launch_time else 0
    
    print(task)
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

            result = await func(*args[:-1], parent_tool or task.workflow, task_args, task.env)
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

        return task_update

    except Exception as error:
        task_update = {
            "status": "failed",
            "error": str(error)
        }
        
        n_samples = task.args.get("n_samples", 1)
        refund_amount = (task.cost or 0) * (n_samples - len(task.result or [])) / n_samples
        user = User.load(task.user, env=task.env)
        user.refund_manna(refund_amount)
        
        return {"status": "failed", "error": str(error)}

    finally:
        run_time = datetime.utcnow() - start_time
        task_update["performance"] = {
            "waitTime": queue_time,
            "runTime": run_time.total_seconds()
        }
        task.update(**task_update)
        #self.launch_time = 0



# @tool_handler_func
# async def process_image(tool: str, args: Dict, env: str):
#     return {
#         "output": args["image_url"]
#     }

# async def _tool_handler(func, *args, **kwargs):
#     if len(args) >= 3:
#         tool, args_, env = args[-3:]
#         args = args[:-3]
#     else:
#         tool = kwargs.get('tool')
#         args_ = kwargs.get('args')
#         env = kwargs.get('env')

#     result = await func(*args, tool, args_, env)
#     result = eden_utils.upload_result(result, env=env)
#     return result

# def tool_handler_func(func):
#     @wraps(func)
#     async def wrapper(tool: str, args: Dict, env: str):
#         return await _tool_handler(func, tool, args, env)
#     return wrapper

# def tool_handler_method(func):
#     @wraps(func)
#     async def wrapper(self, tool: str, args: Dict, env: str):
#         return await _tool_handler(func, self, tool, args, env)
#     return wrapper







class User(MongoModel):
    userId: str
    isWeb2: bool
    isAdmin: bool
    username: str
    userImage: str
    email: Optional[str] = None
    normalizedEmail: Optional[str] = None
    featureFlags: List[str]
    subscriptionTier: Optional[int] = None
    highestMonthlySubscriptionTier: Optional[int] = None
    deleted: bool    
    # mannas: SkipJsonSchema[Optional[Collection]] = Field(None, exclude=True)

    # def __init__(self, env, **data):
    #     super().__init__(env=env, **data)
    #     self.mannas = get_collection("mannas", env=env)
    #     if not self.mannas.find_one({"user": self.id}):
    #         raise Exception("Mannas not found")
    
    @classmethod
    def get_collection_name(cls) -> str:
        return "users"
    
    def verify_manna_balance(self, amount: float):
        mannas = get_collection("mannas", env=self.env)
        manna = mannas.find_one({"user": self.id})
        if not manna:
            raise Exception("Mannas not found")
        balance = manna.get("balance") + manna.get("subscriptionBalance", 0)
        if balance < amount:
            raise Exception(f"Insufficient manna balance. Need {amount} but only have {balance}")

    def spend_manna(self, amount: float):
        if amount == 0:
            return
        # manna = self.mannas.find_one({"user": self.id})
        mannas = get_collection("mannas", env=self.env)
        manna = mannas.find_one({"user": self.id})
        if not manna:
            raise Exception("Mannas not found")
        subscription_balance = manna.get("subscriptionBalance", 0)
        # Use subscription balance first
        if subscription_balance > 0:
            subscription_spend = min(subscription_balance, amount)
            mannas.update_one(
                {"user": self.id},
                {"$inc": {"subscriptionBalance": -subscription_spend}}
            )
            amount -= subscription_spend
        # If there's remaining amount, use regular balance
        if amount > 0:
            mannas.update_one(
                {"user": self.id},
                {"$inc": {"balance": -amount}}
            )
        
    def refund_manna(self, amount: float):
        if amount == 0:
            return
        # todo: make it refund to subscription balance first
        mannas = get_collection("mannas", env=self.env)
        mannas.update_one({"user": self.id}, {"$inc": {"balance": amount}})

