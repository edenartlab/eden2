import os
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, Field, ValidationError
from pydantic.json_schema import SkipJsonSchema
from pymongo import MongoClient
from pymongo.collection import Collection

from dotenv import load_dotenv
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION_NAME = os.getenv("AWS_REGION_NAME")
AWS_BUCKET_NAME_STAGE = os.getenv("AWS_BUCKET_NAME_STAGE")
AWS_BUCKET_NAME_PROD = os.getenv("AWS_BUCKET_NAME_PROD")
MONGO_DB_NAME_STAGE = os.getenv("MONGO_DB_NAME_STAGE")
MONGO_DB_NAME_PROD = os.getenv("MONGO_DB_NAME_PROD")

envs = {
    "STAGE": {
        "bucket_name": AWS_BUCKET_NAME_STAGE,
        "db_name": MONGO_DB_NAME_STAGE,
    },
    "PROD": {
        "bucket_name": AWS_BUCKET_NAME_PROD,
        "db_name": MONGO_DB_NAME_PROD,
    }
}

mongo_client = MongoClient(MONGO_URI)


class MongoBaseModel(BaseModel):
    id: SkipJsonSchema[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    createdAt: datetime = Field(default_factory=datetime.now(datetime.UTC), exclude=True)
    updatedAt: datetime = Field(default_factory=datetime.now(datetime.UTC), exclude=True)    
    collection: SkipJsonSchema[Collection] = Field(None, exclude=True)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        protected_namespaces = ()

    def __init__(self, collection_name: str, env: str, **data):
        super().__init__(**data)
        db_name = envs[env]["db_name"]
        self.collection = mongo_client[db_name][collection_name]

    @staticmethod
    def from_id(cls, document_id, collection_name, env):
        db_name = envs[env]["db_name"]
        collection = mongo_client[db_name][collection_name]
        document_id = document_id if isinstance(document_id, ObjectId) else ObjectId(document_id)
        document = collection.find_one({"_id": document_id})
        if not document:
            raise Exception("Document not found")
        return cls(**document, collection=collection, env=env)

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

    def reload(self): 
        if self.collection is None:
            raise Exception("Collection not set")

        document = self.collection.find_one({"_id": self.id})
        if not document:
            raise Exception("Document not found")
        for key, value in document.items():
            setattr(self, key, value)
        return self

    def save(self):
        if self.collection is None:
            raise Exception("Collection not set")

        try:
            self.model_validate(self)
        except ValidationError as e:
            print("Validation error:", e)
            return None

        data = self.to_mongo()
        document_id = data.get('_id')

        if document_id:
            data["updatedAt"] = datetime.now(datetime.UTC)
            return self.collection.update_one({'_id': document_id}, {'$set': data}, upsert=True)
        else:
            return self.collection.insert_one(data)

    def update(self, update_args):
        if self.collection is None:
            raise Exception("Collection not set")

        try:
            # self.model_validate({**self.to_mongo(), **update_args}) #, "db_name": self.collection.database.name})
            self.model_validate({**self.to_mongo(), **update_args, "env": "STAGE"})
        except ValidationError as e:
            print("Validation error:", e)
            return None

        data = self.to_mongo()
        document_id = data.get('_id')

        if document_id:
            update_args["updatedAt"] = datetime.now(datetime.UTC)
            return self.collection.update_one({'_id': document_id}, {'$set': update_args})
        else:
            raise Exception("Document not found")
