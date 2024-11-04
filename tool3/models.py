from bson import ObjectId
from typing import Dict, Any, Optional, List
from pymongo.collection import Collection
from pydantic.json_schema import SkipJsonSchema
from pydantic import Field, BaseModel

from mongo import MongoModel, get_collection


from functools import wraps
from datetime import datetime
from pprint import pprint
import eden_utils



class Model(MongoModel):
    name: str
    user: ObjectId
    slug: str = None
    args: Dict[str, Any]
    task: ObjectId
    public: bool = False
    checkpoint: str
    base_model: str
    thumbnail: str
    # users: SkipJsonSchema[Optional[Collection]] = Field(None, exclude=True)

    # def __init__(self, env, **data):
    #     super().__init__(collection_name="models", env=env, **data)
    #     # self.users = get_collection("users", env=env)
    #     self._make_slug()

    def __init__(self, env, **data):
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
        if self.collection is None:
            return
        if self.slug:
            # slug already assigned
            return
        name = self.name.lower().replace(" ", "-")
        existing_docs = list(self.collection.find({"name": self.name, "user": self.user}))
        versions = [int(doc.get('slug', '').split('/')[-1][1:]) for doc in existing_docs if doc.get('slug')]
        new_version = max(versions or [0]) + 1
        users = get_collection("users", env=self.env)
        username = users.find_one({"_id": self.user})["username"]
        # username = self.users.find_one({"_id": self.user})["username"]
        self.slug = f"{username}/{name}/v{new_version}"

    def save(self, **kwargs):
        self._make_slug()
        super().save(**kwargs)
    
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
    status: str = "pending"
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

    start_time = datetime.utcnow()
    queue_time = (start_time - task.createdAt).total_seconds()
    #boot_time = queue_time - self.launch_time if self.launch_time else 0
    
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

            result = await func(*args[:-1], task.workflow, task_args, task.env)
            result = eden_utils.prepare_result(result, env=task.env)
            results.extend(result)
            
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
    mannas: SkipJsonSchema[Optional[Collection]] = Field(None, exclude=True)

    def __init__(self, env, **data):
        super().__init__(env=env, **data)
        self.mannas = get_collection("mannas", env=env)
        if not self.mannas.find_one({"user": self.id}):
            raise Exception("Mannas not found")
    
    @classmethod
    def get_collection_name(cls) -> str:
        return "users"
    
    def verify_manna_balance(self, amount: float):
        manna = self.mannas.find_one({"user": self.id})
        balance = manna.get("balance") + manna.get("subscriptionBalance", 0)
        if balance < amount:
            raise Exception(f"Insufficient manna balance. Need {amount} but only have {balance}")

    def spend_manna(self, amount: float):
        if amount == 0:
            return
        manna = self.mannas.find_one({"user": self.id})
        subscription_balance = manna.get("subscriptionBalance", 0)
        # Use subscription balance first
        if subscription_balance > 0:
            subscription_spend = min(subscription_balance, amount)
            self.mannas.update_one(
                {"user": self.id},
                {"$inc": {"subscriptionBalance": -subscription_spend}}
            )
            amount -= subscription_spend
        # If there's remaining amount, use regular balance
        if amount > 0:
            self.mannas.update_one(
                {"user": self.id},
                {"$inc": {"balance": -amount}}
            )
        
    def refund_manna(self, amount: float):
        if amount == 0:
            return
        # todo: make it refund to subscription balance first
        self.mannas.update_one({"user": self.id}, {"$inc": {"balance": amount}})
