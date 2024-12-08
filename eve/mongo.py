import os
import copy
import yaml
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from pydantic.json_schema import SkipJsonSchema
from pymongo import MongoClient
from datetime import datetime, UTC, timezone
from bson import ObjectId
from abc import abstractmethod
from typing import Annotated, Optional

from pydantic import BaseModel, Field, ValidationError
from pymongo import MongoClient
from bson import ObjectId
from typing import Optional, List, Dict, Any, Union

from .base import generate_edit_model, recreate_base_model, VersionableBaseModel


MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME_STAGE = os.getenv("MONGO_DB_NAME_STAGE")
MONGO_DB_NAME_PROD = os.getenv("MONGO_DB_NAME_PROD")

db_names = {
    "STAGE": MONGO_DB_NAME_STAGE,
    "PROD": MONGO_DB_NAME_PROD,
}

if not all([MONGO_URI, MONGO_DB_NAME_STAGE, MONGO_DB_NAME_PROD]):
    raise ValueError("MONGO_URI, MONGO_DB_NAME_STAGE, and MONGO_DB_NAME_PROD must be set in the environment")

def get_collection(collection_name: str, db: str):
    mongo_client = MongoClient(MONGO_URI)
    db_name = db_names[db]
    return mongo_client[db_name][collection_name]

def Collection(name):
    def wrapper(cls):
        cls.collection_name = name
        return cls
    return wrapper


class Document(BaseModel):
    id: Optional[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    createdAt: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: Optional[datetime] = None
    db: Optional[str] = None

    class Config:
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat(),
        }
        populate_by_name = True
        arbitrary_types_allowed = True

    @classmethod
    def get_collection(cls, db=None):
        """
        Override this method to provide the correct collection for the model.
        """
        db = db or cls.db or "STAGE"
        collection_name = getattr(cls, "collection_name", cls.__name__.lower())
        return get_collection(collection_name, db)

    @classmethod
    def from_schema(cls, schema: dict, db="STAGE", from_yaml=True):
        schema["db"] = db
        sub_cls = cls.get_sub_class(schema, from_yaml=from_yaml, db=db)
        return sub_cls.model_validate(schema)

    @classmethod
    def from_yaml(cls, file_path: str, db="STAGE"):
        """
        Load a document from a YAML file.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {file_path} not found")
        with open(file_path, "r") as file:
            schema = yaml.safe_load(file)
        schema["key"] = schema.get("key") or file_path.split("/")[-2]
        sub_cls = cls.get_sub_class(schema, from_yaml=True, db=db)
        schema = sub_cls.convert_from_yaml(schema, file_path=file_path)
        return cls.from_schema(schema, db=db, from_yaml=True)

    @classmethod
    def from_mongo(cls, document_id: ObjectId, db="STAGE"):
        """
        Load the document from the database and return an instance of the model.
        """
        document_id = document_id if isinstance(document_id, ObjectId) else ObjectId(document_id)
        schema = cls.get_collection(db).find_one({"_id": document_id})
        if not schema:
            raise ValueError(f"Document {document_id} not found in {cls.collection_name}:{db}")        
        sub_cls = cls.get_sub_class(schema, from_yaml=False, db=db)
        schema = sub_cls.convert_from_mongo(schema)
        return cls.from_schema(schema, db, from_yaml=False)
        
    @classmethod
    def load(cls, key: str, db="STAGE"):
        """
        Load the document from the database and return an instance of the model.
        """
        schema = cls.get_collection(db).find_one({"key": key})
        if not schema:
            raise ValueError(f"Document with key {key} not found in {cls.collection_name}:{db}")        
        sub_cls = cls.get_sub_class(schema, from_yaml=False, db=db)
        schema = sub_cls.convert_from_mongo(schema)
        return cls.from_schema(schema, db, from_yaml=False)
        
    @classmethod
    def get_sub_class(cls, schema: dict = None, db="STAGE", from_yaml=True) -> type:
        return cls

    @classmethod
    def convert_from_mongo(cls, schema: dict, **kwargs):
        return schema

    @classmethod
    def convert_from_yaml(cls, schema: dict, **kwargs) -> dict:
        return schema

    @classmethod
    def convert_to_mongo(cls, schema: dict, **kwargs):
        return schema

    @classmethod
    def convert_to_yaml(cls, schema: dict, **kwargs) -> dict:
        return schema

    def save(self, db=None, upsert_filter=None, **kwargs):
        """
        Save the current state of the model to the database.
        """
        db = db or self.db or "STAGE"        
        filter = upsert_filter or {"_id": self.id}

        schema = self.model_dump(by_alias=True, exclude={"db"})
        self.model_validate(schema)
        schema = self.convert_to_mongo(schema)
        schema.update(kwargs)
        schema.pop("_id")

        self.updatedAt = datetime.now(timezone.utc)
        collection = self.get_collection(db)
        if self.id:
            collection.replace_one(filter, schema, upsert=True)
        else:
            self.createdAt = datetime.now(timezone.utc)
            result = collection.insert_one(schema)
            self.id = result.inserted_id
        self.db = db

    # todo: this method is probably superfluous, should remove
    # def validate_fields(self):
    #     """
    #     Validate fields using Pydantic's built-in validation.
    #     """
    #     return self.model_validate(self.model_dump())

    def update(self, **kwargs):
        """
        Perform granular updates on specific fields.
        """
        # updated_data = self.model_copy(update=kwargs)
        # updated_data.validate_fields()  # todo: check this, it's probably unnecessary
        collection = self.get_collection(self.db)
        update_result = collection.update_one(
            {"_id": self.id}, 
            {
                "$set": kwargs,
                "$currentDate": {"updatedAt": True}
            }
        )
        if update_result.modified_count > 0:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def set_against_filter(self, updates: Dict = None, filter: Optional[Dict] = None):
        """
        Perform granular updates on specific fields, given an optional filter.
        """
        collection = self.get_collection(self.db)
        update_result = collection.update_one(
            {"_id": self.id, **filter},
            {
                "$set": updates,
                "$currentDate": {"updatedAt": True}
            }
        )
        if update_result.modified_count > 0:
            self.updatedAt = datetime.now(timezone.utc)

    def push(self, field_name: str, value: Union[Any, List[Any]]):
        """
        Push one or more values to an array field in the document, with validation.
        If the value is a Pydantic model, it will be converted to a dictionary before saving.
        """
        values_to_push = value if isinstance(value, list) else [value]

        # Convert Pydantic models to dictionaries if needed
        values_original = [copy.deepcopy(v) for v in values_to_push]
        values_to_push = [v.model_dump() if isinstance(v, BaseModel) else v for v in values_to_push]
        
        # Create a copy of the current instance and update the array field with the new values for validation
        updated_data = copy.deepcopy(self)
        if hasattr(updated_data, field_name) and isinstance(getattr(updated_data, field_name), list):
            getattr(updated_data, field_name).extend(values_original)
            # updated_data.validate_fields()
        else:
            raise ValidationError(f"Field '{field_name}' is not a valid list field.")

        # Perform the push operation if validation passes
        collection = self.get_collection(self.db)
        update_result = collection.update_one(
            {"_id": self.id},
            {"$push": {field_name: {"$each": values_to_push}}, "$currentDate": {"updatedAt": True}}
        )
        if update_result.modified_count > 0:
            if hasattr(self, field_name) and isinstance(getattr(self, field_name), list):
                setattr(self, field_name, getattr(self, field_name) + values_original)
                self.updatedAt = datetime.now(timezone.utc)

    def update_nested_field(self, field_name: str, index: int, sub_field: str, value):
        """
        Update a specific field within an array of dictionaries, both in MongoDB and in the local instance.
        """
        # Create a copy of the current instance and update the nested field for validation
        updated_data = self.model_copy()
        if hasattr(updated_data, field_name) and isinstance(getattr(updated_data, field_name), list):
            field_list = getattr(updated_data, field_name)
            if len(field_list) > index and isinstance(field_list[index], dict):
                field_list[index][sub_field] = value
                # updated_data.validate_fields()
            else:
                raise ValidationError(f"Field '{field_name}[{index}]' is not a valid dictionary field.")
        else:
            raise ValidationError(f"Field '{field_name}' is not a valid list field.")

        # Perform the update operation in MongoDB
        collection = self.get_collection(self.db)
        update_result = collection.update_one(
            {"_id": self.id},
            {"$set": {
                f"{field_name}.{index}.{sub_field}": value}, 
                "$currentDate": {"updatedAt": True}
            }
        )
        if update_result.modified_count > 0:
            # Update the value in the local instance if the update was successful
            if hasattr(self, field_name) and isinstance(getattr(self, field_name), list):
                field_list = getattr(self, field_name)
                if len(field_list) > index and isinstance(field_list[index], dict):
                    field_list[index][sub_field] = value
                    self.updatedAt = datetime.now(timezone.utc)

    def reload(self):
        """
        Reload the current document from the database to ensure the instance is up-to-date.
        """
        updated_instance = self.from_mongo(self.id, self.db)
        if updated_instance:
            for key, value in updated_instance.dict().items():
                setattr(self, key, value)

    def delete(self):
        """
        Delete the document from the database.
        """
        collection = self.get_collection(self.db)
        collection.delete_one({"_id": self.id})






##### Old, deprecated

class MongoModel(BaseModel):
    id: Annotated[ObjectId, Field(default_factory=ObjectId, alias="_id")]
    db: SkipJsonSchema[str] = Field(..., exclude=True)
    createdAt: datetime = Field(default_factory=lambda: datetime.utcnow().replace(microsecond=0))
    updatedAt: Optional[datetime] = None

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
                **{"db": self.db},
                **kwargs
            })
        except ValidationError as e:
            raise ValueError(get_human_readable_error(e.errors()))

    @classmethod
    def load(cls, document_id: str, db: str):
        collection = get_collection(cls.get_collection_name(), db)
        document = collection.find_one({"_id": ObjectId(document_id)})
        if document is None:
            raise ValueError(f"Document with id {document_id} not found in collection {cls.get_collection_name()}, db: {db}")
        document['db'] = db
        return cls.model_validate(document)

    def reload(self): 
        collection = get_collection(self.get_collection_name(), self.db)
        document = collection.find_one({"_id": self.id})
        if not document:
            raise ValueError(f"Document with id {self.id} not found in collection {self.get_collection_name()}, db: {self.db}")
        for key, value in document.items():
            setattr(self, key, value)
        return self

    def save(self, upsert_filter=None):
        self.validate()

        data = self.model_dump(by_alias=True, exclude_none=True)
        collection = get_collection(self.get_collection_name(), self.db)
        
        document_id = data.get('_id')
        if upsert_filter:
            document_id_ = collection.find_one(upsert_filter, {"_id": 1})
            if document_id_:
                document_id = document_id_["_id"]
        else:
            upsert_filter = {"_id": document_id}

        if document_id:
            # data['updatedAt'] = datetime.utcnow().replace(microsecond=0)
            data.pop("updatedAt", None)
            # collection.update_one(upsert_filter, {'$set': data}, upsert=True)
            collection.update_one(
                upsert_filter,
                {
                    "$set": data,
                    "$currentDate": {"updatedAt": True}
                },
                upsert=True
            )
        else:
            # now = datetime.utcnow().replace(microsecond=0)
            # data["createdAt"] = self.createdAt
            # data["updatedAt"] = self.createdAt
            collection.insert_one(data)

    def push(self, payload: dict):
        self.validate()
        collection = get_collection(self.get_collection_name(), self.db)
        collection.update_one(
            {"_id": self.id},
            {
                "$push": payload,
                "$currentDate": {"updatedAt": True}
            }
        )

    def set(self, payload: dict, filter: dict = None):
        self.validate()
        collection = get_collection(self.get_collection_name(), self.db)
        collection.update_one(
            {"_id": self.id, **filter},
            {
                "$set": payload,
                "$currentDate": {"updatedAt": True}
            }
        )
    
    # todo: can this be merged with set? is it redundant?
    # generalize update methods
    def update2(self, **kwargs):
        update_args = {}
        for key, value in kwargs.items():
            if hasattr(self, key) and getattr(self, key) != value:
                update_args[key] = value
        
        if not update_args:
            return self
        
        self.validate(**update_args)
        
        collection = get_collection(self.get_collection_name(), self.db)
        result = collection.update_one(
            {"_id": ObjectId(self.id)},
            {
                "$set": update_args,
                "$currentDate": {"updatedAt": True}
            }
        )        
        
        if result.matched_count == 0:
            raise ValueError(f"Document with id {self.id} not found in collection {self.get_collection_name()}")
        for key, value in update_args.items():
            setattr(self, key, copy.deepcopy(value))
            


    def update(self, payload: dict = None, filter: dict = None, **kwargs):
        """
        Updates both the MongoDB document and instance variables.
        
        Args:
            payload (dict): Nested updates using dot notation (e.g., {"messages.$.content": "new"})
            filter (dict): Additional filter criteria for the update
            **kwargs: Direct field updates (e.g., name="new_name")
        """
        # Combine payload and kwargs into a single update dictionary
        updates = {}
        
        # Handle nested updates from payload (using dot notation)
        if payload:
            updates.update(payload)
        
        # Handle direct field updates from kwargs
        for key, value in kwargs.items():
            if hasattr(self, key) and getattr(self, key) != value:
                updates[key] = value
        
        if not updates:
            return self
        
        # Validate the updates
        self.validate(**{k.split('.')[-1]: v for k, v in updates.items()})
        
        # Perform MongoDB update
        collection = get_collection(self.get_collection_name(), self.db)
        result = collection.update_one(
            {"_id": self.id, **(filter or {})},
            {
                "$set": updates,
                "$currentDate": {"updatedAt": True}
            }
        )
        
        if result.matched_count == 0:
            raise ValueError(f"Document with id {self.id} not found in collection {self.get_collection_name()}")
        
        # Update instance variables for non-nested fields
        for key, value in updates.items():
            if '.' not in key:  # Only update non-nested fields
                setattr(self, key, copy.deepcopy(value))
        
        return self




class VersionableMongoModel(VersionableBaseModel):
    id: Annotated[ObjectId, Field(default_factory=ObjectId, alias="_id")]
    collection_name: SkipJsonSchema[str] = Field(..., exclude=True)
    db: SkipJsonSchema[str] = Field(..., exclude=True)
    # createdAt: datetime = Field(default_factory=lambda: datetime.utcnow().replace(microsecond=0))
    # updatedAt: Optional[datetime] = None #Field(default_factory=lambda: datetime.utcnow().replace(microsecond=0))

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    def __init__(self, **data):
        if 'instance' in data:
            instance = data.pop('instance')
            collection_name = data.pop('collection_name')
            db = data.pop('db')
            super().__init__(
                schema=type(instance),
                initial=instance,
                current=instance,
                collection_name=collection_name,
                db=db,
                **data
            )
        else:
            super().__init__(**data)

    @classmethod
    def load(cls, document_id: str, collection_name: str, db: str):
        collection = get_collection(collection_name, db)
        document = collection.find_one({"_id": ObjectId(document_id)})
        if document is None:
            raise ValueError(f"Document with id {document_id} not found in collection {collection_name}, db: {db}")
        
        schema = recreate_base_model(document['schema'])
        initial = schema(**document['initial'])
        current = schema(**document['current'])
        
        edits = [
            generate_edit_model(schema)(**edit) 
            for edit in document['edits']
        ]
        
        versionable_data = {
            "id": document['_id'],
            "collection_name": collection_name, 
            "db": db,
            # "createdAt": document['createdAt'],
            # "updatedAt": document['updatedAt'],
            "schema": schema,
            "initial": initial,
            "current": current,
            "edits": edits
        }
        
        return cls(**versionable_data)

    def save(self, upsert_filter=None):
        data = self.model_dump(by_alias=True, exclude_none=True)
        collection = get_collection(self.collection_name, self.db)

        document_id = data.get('_id')
        if upsert_filter:
            document_id_ = collection.find_one(upsert_filter, {"_id": 1})
            if document_id_:
                document_id = document_id_["_id"]

        if document_id:
            # data['updatedAt'] = datetime.utcnow().replace(microsecond=0)
            collection.update_one({'_id': document_id}, {'$set': data}, upsert=True)
        else:
            collection.insert_one(data)
