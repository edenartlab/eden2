import os
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, Field, ValidationError
from pydantic.json_schema import SkipJsonSchema
from pymongo import MongoClient


load_dotenv()
env = os.getenv("ENV", "STAGE").lower()
mongo_url = os.getenv("MONGO_URI")

client = MongoClient(mongo_url)
db_name = "eden-prod" if env == "prod" else "eden-stg"
db = client[db_name]

threads = db["threads"]
agents = db["agents"]
users = db["users"]
api_keys = db["apikeys"]
models = db["models"]
tasks = db["tasks2"]
characters = db["characters"]


class MongoBaseModel(BaseModel):
    id: SkipJsonSchema[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    createdAt: datetime = Field(default_factory=datetime.utcnow, exclude=True)
    updatedAt: datetime = Field(default_factory=datetime.utcnow, exclude=True)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        protected_namespaces = ()

    @staticmethod
    def from_id(cls, collection, document_id):
        document_id = document_id if isinstance(document_id, ObjectId) else ObjectId(document_id)
        document = collection.find_one({"_id": document_id})
        if not document:
            raise Exception("Document not found")
        return cls(**document)

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
        try:
            cls.validate(document)
        except ValidationError as e:
            print("Validation error:", e)
            return None

        data = document.to_mongo()
        document_id = data.get('_id')

        if document_id:
            data["updatedAt"] = datetime.utcnow()
            return collection.update_one({'_id': document_id}, {'$set': data}, upsert=True)
        else:
            return collection.insert_one(data)

    @classmethod
    def update(cls, document, collection, update_args):
        try:
            cls.validate({**document.to_mongo(), **update_args})
        except ValidationError as e:
            print("Validation error:", e)
            return None

        data = document.to_mongo()
        document_id = data.get('_id')

        if document_id:
            update_args["updatedAt"] = datetime.utcnow()
            return collection.update_one({'_id': document_id}, {'$set': update_args})
        else:
            raise Exception("Document not found")
