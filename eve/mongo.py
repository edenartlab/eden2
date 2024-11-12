import os
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, Field, ValidationError
from pydantic.json_schema import SkipJsonSchema
from pymongo import MongoClient
from pymongo.collection import Collection
from dotenv import load_dotenv
from eden_utils import deep_filter, deep_update
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME_STAGE = os.getenv("MONGO_DB_NAME_STAGE")
MONGO_DB_NAME_PROD = os.getenv("MONGO_DB_NAME_PROD")
MONGO_DB_NAME_ABRAHAM = os.getenv("MONGO_DB_NAME_ABRAHAM")

db_names = {
    "STAGE": MONGO_DB_NAME_STAGE,
    "PROD": MONGO_DB_NAME_PROD,
    "ABRAHAM": MONGO_DB_NAME_ABRAHAM
}

mongo_client = MongoClient(MONGO_URI)

def get_collection(collection_name: str, env: str):
    db_name = db_names[env]
    return mongo_client[db_name][collection_name]

class MongoBaseModel(BaseModel):
    id: SkipJsonSchema[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    createdAt: datetime = Field(default_factory=datetime.utcnow, exclude=True)
    updatedAt: datetime = Field(default_factory=datetime.utcnow, exclude=True)    
    collection: SkipJsonSchema[Collection] = Field(None, exclude=True)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        protected_namespaces = ()

    def __init__(self, collection_name: str, env: str, **data):
        data["collection"] = get_collection(collection_name, env)
        super().__init__(**data)

    @staticmethod
    def from_id(cls, document_id, collection_name, env):
        document_id = document_id if isinstance(document_id, ObjectId) else ObjectId(document_id)
        collection = get_collection(collection_name, env)
        document = collection.find_one({"_id": document_id})
        if not document:
            raise Exception(f"Document {document_id} not found in {env} collection {collection_name}")
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

    def save(self, upsert_query=None):
        if self.collection is None:
            raise Exception("Collection not set")

        self.model_validate(self)

        data = self.to_mongo()
        document_id = data.get('_id')

        # upsert query overrides ID if it exists
        if upsert_query:
            document_id_ = self.collection.find_one(upsert_query, {"_id": 1})
            if document_id_:
                document_id = document_id_["_id"]
            data["_id"] = ObjectId(document_id)

        if document_id:
            data["updatedAt"] = datetime.utcnow()
            self.collection.update_one({'_id': document_id}, {'$set': data}, upsert=True)
        else:
            return self.collection.insert_one(data)

    def update(self, update_args):
        if self.collection is None:
            raise Exception("Collection not set")

        self.model_validate({**self.to_mongo(), **update_args, "env": "STAGE"})

        if not self.collection.find_one({"_id": self.id}):
            self.save()

        update_args["updatedAt"] = datetime.utcnow()

        return self.collection.update_one({'_id': self.id}, {'$set': update_args})








"""
Everything below this is experimental
"""



class VersionedMongoBaseModel(MongoBaseModel):
    current: dict = Field(default_factory=dict)
    versions: list[dict] = Field(default_factory=list)

    # def __init__(self, collection_name, env, **data):
    #     super().__init__(collection_name=collection_name, env=env)
    #     self.update(data)

    def update_current(self, changes):
        if self.collection is None:
            raise Exception("Collection not set")

        changes = deep_filter(self.current, changes)
        if not changes:
            return

        # print("===========")
        # print("self.current", self.current.copy())
        # print("changes", changes)
        
        next = deep_update(self.current.copy(), changes)
        # print("next", next)
        # print("===========")
        
        self.validate_data(next)
        self.current = next

        update_operation = {
            "$set": {
                "current": self.current,
                "updatedAt": datetime.utcnow()
            },
            "$push": {
                "versions": {
                    "data": changes,
                    "timestamp": datetime.utcnow()
                }
            }
        }
        # print("update_operation", update_operation)
        # print(self.id)
        # print(self.collection)
        
        
        if not self.collection.find_one({"_id": self.id}):
            self.save()

        self.collection.update_one(
            {"_id": self.id},
            update_operation
        )

    def reconstruct_version(self, target_time):
        reconstructed = {}
        for version in self.versions:
            if version["timestamp"] <= target_time:
                reconstructed.update(version["data"])
            else:
                break        
        return reconstructed



class VersionedMongoBaseModel2(MongoBaseModel):
    current: dict = Field(default_factory=dict)
    versions: list[dict] = Field(default_factory=list)

    # def __init__(self, collection_name, env, **data):
    #     super().__init__(collection_name=collection_name, env=env)
    #     self.update(data)

    def update_current(self, changes):
        if self.collection is None:
            raise Exception("Collection not set")

        changes = deep_filter(self.current, changes)
        if not changes:
            return

        # print("===========")
        # print("self.current", self.current.copy())
        # print("changes", changes)
        
        next = deep_update(self.current.copy(), changes)
        # print("next", next)
        # print("===========")
        
        self.validate_data(next)
        self.current = next

        update_operation = {
            "$set": {
                "current": self.current,
                "updatedAt": datetime.utcnow()
            },
            "$push": {
                "versions": {
                    "data": changes,
                    "timestamp": datetime.utcnow()
                }
            }
        }
        # print("update_operation", update_operation)
        # print(self.id)
        # print(self.collection)
        
        
        if not self.collection.find_one({"_id": self.id}):
            self.save()

        self.collection.update_one(
            {"_id": self.id},
            update_operation
        )

    def reconstruct_version(self, target_time):
        reconstructed = {}
        for version in self.versions:
            if version["timestamp"] <= target_time:
                reconstructed.update(version["data"])
            else:
                break        
        return reconstructed
    


"""
from models import Story
story = Story.from_id("66de2dfa5286b9dc656291c1", env="STAGE")
print(story.current)
story.update({"screenplay": {"scenes": "test"}})

import json
from tool import load_tool
t = load_tool("tools/write")
print(json.dumps(t.openai_tool_schema(), indent=2))

"""
