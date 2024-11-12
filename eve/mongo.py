import os
import copy
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from pydantic.json_schema import SkipJsonSchema
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId
from abc import abstractmethod
from typing import Annotated

from .base import generate_edit_model, recreate_base_model, VersionableBaseModel

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME_STAGE = os.getenv("MONGO_DB_NAME_STAGE")
MONGO_DB_NAME_PROD = os.getenv("MONGO_DB_NAME_PROD")
MONGO_DB_NAME_ABRAHAM = os.getenv("MONGO_DB_NAME_ABRAHAM")

db_names = {
    "STAGE": MONGO_DB_NAME_STAGE,
    "PROD": MONGO_DB_NAME_PROD,
    "ABRAHAM": MONGO_DB_NAME_ABRAHAM
}

# todo: this requires internet upon import
# make it so only when imported it connects
# mongo_client = MongoClient(MONGO_URI)

def get_collection(collection_name: str, env: str):
    db_name = db_names[env]
    mongo_client = MongoClient(MONGO_URI)
    return mongo_client[db_name][collection_name]


def get_human_readable_error(error_list):
    errors = [f"{error['loc'][0]}: {error['msg']}" for error in error_list]
    error_str = "\n\t".join(errors)
    error_str = f"Invalid args\n\t{error_str}"
    return error_str


class MongoModel(BaseModel):
    id: Annotated[ObjectId, Field(default_factory=ObjectId, alias="_id")]
    env: SkipJsonSchema[str] = Field(..., exclude=True)
    createdAt: datetime = Field(default_factory=lambda: datetime.utcnow().replace(microsecond=0))
    updatedAt: datetime = Field(default_factory=lambda: datetime.utcnow().replace(microsecond=0))

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    @classmethod
    @abstractmethod
    def get_collection_name(cls) -> str:
        pass

    def validate(self, **kwargs):
        try:
            super().model_validate({
                **self.model_dump(), 
                **{"env": self.env},
                **kwargs
            })
        except ValidationError as e:
            raise ValueError(get_human_readable_error(e.errors()))

    @classmethod
    def load(cls, document_id: str, env: str):
        collection = get_collection(cls.get_collection_name(), env)
        document = collection.find_one({"_id": ObjectId(document_id)})
        if document is None:
            raise ValueError(f"Document with id {document_id} not found in collection {cls.get_collection_name()}, env: {env}")
        document['env'] = env
        return cls.model_validate(document)

    def reload(self): 
        collection = get_collection(self.get_collection_name(), self.env)
        document = collection.find_one({"_id": self.id})
        if not document:
            raise ValueError(f"Document with id {self.id} not found in collection {self.get_collection_name()}, env: {self.env}")
        for key, value in document.items():
            setattr(self, key, value)
        return self

    def save(self, upsert_query=None):
        self.validate()

        data = self.model_dump(by_alias=True, exclude_none=True)
        collection = get_collection(self.get_collection_name(), self.env)
        
        document_id = data.get('_id')
        if upsert_query:
            document_id_ = collection.find_one(upsert_query, {"_id": 1})
            if document_id_:
                document_id = document_id_["_id"]
        else:
            upsert_query = {"_id": document_id}

        if document_id:
            data['updatedAt'] = datetime.utcnow().replace(microsecond=0)
            collection.update_one(upsert_query, {'$set': data}, upsert=True)
        else:
            collection.insert_one(data)
    
    def update(self, **kwargs):
        update_args = {}
        for key, value in kwargs.items():
            if hasattr(self, key) and getattr(self, key) != value:
                update_args[key] = value
        if not update_args:
            return self
        self.validate(**update_args)        
        update_args['updatedAt'] = datetime.utcnow().replace(microsecond=0)        
        result = get_collection(self.get_collection_name(), self.env).update_one(
            {"_id": ObjectId(self.id)},
            {"$set": update_args}
        )        
        if result.matched_count == 0:
            raise ValueError(f"Document with id {self.id} not found in collection {self.get_collection_name()}")
        for key, value in update_args.items():
            setattr(self, key, copy.deepcopy(value))
        

class VersionableMongoModel(VersionableBaseModel):
    id: Annotated[ObjectId, Field(default_factory=ObjectId, alias="_id")]
    collection_name: SkipJsonSchema[str] = Field(..., exclude=True)
    env: SkipJsonSchema[str] = Field(..., exclude=True)
    createdAt: datetime = Field(default_factory=lambda: datetime.utcnow().replace(microsecond=0))
    updatedAt: datetime = Field(default_factory=lambda: datetime.utcnow().replace(microsecond=0))

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    def __init__(self, **data):
        if 'instance' in data:
            instance = data.pop('instance')
            collection_name = data.pop('collection_name')
            env = data.pop('env')
            super().__init__(
                schema=type(instance),
                initial=instance,
                current=instance,
                collection_name=collection_name,
                env=env,
                **data
            )
        else:
            super().__init__(**data)

    @classmethod
    def load(cls, document_id: str, collection_name: str, env: str):
        collection = get_collection(collection_name, env)
        document = collection.find_one({"_id": ObjectId(document_id)})
        if document is None:
            raise ValueError(f"Document with id {document_id} not found in collection {collection_name}, env: {env}")
        
        schema = recreate_base_model(document['schema'])
        initial = schema(**document['initial'])
        current = schema(**document['current'])
        
        edits = [generate_edit_model(schema)(**edit) for edit in document['edits']]
        
        versionable_data = {
            "id": document['_id'],
            "collection_name": collection_name, 
            "env": env,
            "createdAt": document['createdAt'],
            "updatedAt": document['updatedAt'],
            "schema": schema,
            "initial": initial,
            "current": current,
            "edits": edits
        }
        
        return cls(**versionable_data)

    def save(self, upsert_query=None):
        data = self.model_dump(by_alias=True, exclude_none=True)
        collection = get_collection(self.collection_name, self.env)

        document_id = data.get('_id')
        if upsert_query:
            document_id_ = collection.find_one(upsert_query, {"_id": 1})
            if document_id_:
                document_id = document_id_["_id"]

        if document_id:
            data['updatedAt'] = datetime.utcnow().replace(microsecond=0)
            collection.update_one({'_id': document_id}, {'$set': data}, upsert=True)
        else:
            collection.insert_one(data)
