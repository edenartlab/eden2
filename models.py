from bson import ObjectId
from typing import Dict, Any, Optional
from pymongo.collection import Collection
from pydantic.json_schema import SkipJsonSchema
from pydantic import Field

from mongo import MongoBaseModel, mongo_client, envs


class Model(MongoBaseModel):
    name: str
    user: ObjectId
    slug: str = None
    args: Dict[str, Any]
    task: ObjectId
    public: bool = False
    checkpoint: str
    thumbnail: str
    users: SkipJsonSchema[Optional[Collection]] = Field(None, exclude=True)

    def __init__(self, env, **data):
        super().__init__(collection_name="models", env=env, **data)
        db_name = envs[env]["db_name"]
        self.users = mongo_client[db_name]["users"] 
        self._make_slug()

    @classmethod
    def from_id(self, document_id: str, env: str):
        db_name = envs[env]["db_name"]
        self.users = mongo_client[db_name]["users"]
        return super().from_id(self, document_id, "models", db_name)

    def _make_slug(self):
        if self.collection is None:
            return
        if self.slug:
            return  # just set it once
        name = self.name.lower().replace(" ", "-")
        version = 1 + self.collection.count_documents({"name": self.name, "user": self.user}) 
        username = self.users.find_one({"_id": self.user})["username"]
        self.slug = f"{username}/{name}/v{version}"


class Task(MongoBaseModel):
    workflow: str
    args: Dict[str, Any]
    user: ObjectId
    handler_id: Optional[str] = None
    status: str = "pending"
    error: Optional[str] = None
    result: Optional[Any] = None
    performance: Optional[Dict[str, Any]] = {}

    def __init__(self, env, **data):
        if isinstance(data.get('user'), str):
            data['user'] = ObjectId(data['user'])
        super().__init__(collection_name="tasks2", env=env, **data)

    @classmethod
    def from_id(self, document_id: str, env: str):
        return super().from_id(self, document_id, "tasks2", env)
