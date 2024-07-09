import os
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema
from pymongo import MongoClient

# from dotenv import load_dotenv
# load_dotenv()
env = os.getenv("ENVIRONMENT")
mongo_url = os.getenv("MONGO_URI")

client = MongoClient(mongo_url)
db_name = "PROD" if env == "PROD" else "STAGE"
db = client[db_name]

threads = db["threads"]
agents = db["agents"]
users = db["users"]
api_keys = db["apikeys"]
models = db["models"]
tasks = db["tasks2"]


class MongoBaseModel(BaseModel):
    id: SkipJsonSchema[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    createdAt: datetime = Field(default_factory=datetime.utcnow, exclude=True)
    updatedAt: datetime = Field(default_factory=datetime.utcnow, exclude=True)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

    @classmethod
    def from_mongo(cls, data: dict):
        return cls(**data)

    def to_mongo(self, **kwargs):
        by_alias = kwargs.pop("by_alias", True)
        exclude = kwargs.pop("exclude", set())
        data = self.model_dump(
            by_alias=by_alias,
            exclude=exclude,
            **kwargs,
        )
        data["_id"] = self.id
        data["createdAt"] = self.createdAt
        data["updatedAt"] = self.updatedAt
        return data

    @classmethod
    def save(cls, document, collection):
        data = document.to_mongo()
        document_id = data.get('_id')
        if document_id:
            data["updated_at"] = datetime.utcnow()
            return collection.update_one({'_id': document_id}, {'$set': data}, upsert=True)
        else:
            return collection.insert_one(data)
            