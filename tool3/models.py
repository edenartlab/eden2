from bson import ObjectId
from typing import Dict, Any, Optional, List
from pymongo.collection import Collection
from pydantic.json_schema import SkipJsonSchema
from pydantic import Field, BaseModel

from mongo import MongoModel, get_collection


# class Model(MongoModel):
#     name: str
#     user: ObjectId
#     slug: str = None
#     args: Dict[str, Any]
#     task: ObjectId
#     public: bool = False
#     checkpoint: str
#     base_model: str
#     thumbnail: str
#     users: SkipJsonSchema[Optional[Collection]] = Field(None, exclude=True)

#     def __init__(self, env, **data):
#         super().__init__(collection_name="models", env=env, **data)
#         self.users = get_collection("users", env=env)
#         self._make_slug()

#     @classmethod
#     def from_id(self, document_id: str, env: str):
#         self.users = get_collection("users", env=env)
#         return super().from_id(self, document_id, "models", env)

#     def _make_slug(self):
#         if self.collection is None:
#             return
#         if self.slug:
#             return
#         name = self.name.lower().replace(" ", "-")
#         existing_docs = list(self.collection.find({"name": self.name, "user": self.user}))
#         versions = [int(doc.get('slug', '').split('/')[-1][1:]) for doc in existing_docs if doc.get('slug')]
#         version = max(versions or [0]) + 1
#         username = self.users.find_one({"_id": self.user})["username"]
#         self.slug = f"{username}/{name}/v{version}"


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
        return super().from_id(self, task["_id"], "tasks2", env)


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
