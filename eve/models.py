from bson import ObjectId
from typing import Dict, Any, Optional, List

from .mongo import MongoModel, get_collection


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

