import os
from dotenv import load_dotenv
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, Field, ValidationError
from pydantic.json_schema import SkipJsonSchema
from pymongo import MongoClient
from pymongo.collection import Collection

load_dotenv()
mongo_url = os.getenv("MONGO_URI")

mongo_client = MongoClient(mongo_url)


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

    def __init__(self, collection_name: str, db_name: str, **data):
        super().__init__(**data)
        self.collection = mongo_client[db_name][collection_name]

    @staticmethod
    def from_id(cls, document_id, collection_name, db_name):
        collection = mongo_client[db_name][collection_name]
        document_id = document_id if isinstance(document_id, ObjectId) else ObjectId(document_id)
        document = collection.find_one({"_id": document_id})
        if not document:
            raise Exception("Document not found")
        return cls(**document, collection=collection, db_name=db_name)

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

    # @classmethod
    def reload(self): 
        if self.collection is None:
            raise Exception("Collection not set")

        document = self.collection.find_one({"_id": self.id})
        if not document:
            raise Exception("Document not found")
        for key, value in document.items():
            setattr(self, key, value)
        return self

    # @classmethod
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
            data["updatedAt"] = datetime.utcnow()
            return self.collection.update_one({'_id': document_id}, {'$set': data}, upsert=True)
        else:
            return self.collection.insert_one(data)

    # @classmethod
    def update(self, update_args):
        if self.collection is None:
            raise Exception("Collection not set")

        try:
            self.model_validate({**self.to_mongo(), **update_args, "db_name": self.collection.database.name})
        except ValidationError as e:
            print("Validation error:", e)
            return None

        data = self.to_mongo()
        document_id = data.get('_id')

        if document_id:
            update_args["updatedAt"] = datetime.utcnow()
            return self.collection.update_one({'_id': document_id}, {'$set': update_args})
        else:
            raise Exception("Document not found")

