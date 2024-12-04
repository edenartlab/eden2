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
MONGO_DB_NAME_ABRAHAM = os.getenv("MONGO_DB_NAME_ABRAHAM")

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


# change to createdAt, updatedAt
class Document(BaseModel):
    id: Optional[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
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
    def from_mongo(cls, document_id: ObjectId, db="STAGE"):
        """
        Load the document from the database and return an instance of the model.
        """
        document_id = document_id if isinstance(document_id, ObjectId) else ObjectId(document_id)
        schema = cls.get_collection(db).find_one({"_id": document_id})
        
        # if data:
        #     instance = cls.model_validate(data)
        #     instance.db = db
        #     return instance
        # return None
        
        if not schema:
            raise ValueError(f"Document {document_id} not found in {cls.collection_name}:{db}")
        
        schema["db"] = db
        schema = cls.convert_from_mongo(schema)

        return cls.model_validate(schema)
    
    
    @classmethod
    def from_yaml(cls, file_path: str):
        """
        Load a document from a YAML file.
        """
        with open(file_path, "r") as file:
            schema = yaml.safe_load(file)
        schema["key"] = file_path.split("/")[-2]
        schema = cls.convert_from_yaml(schema)
        return cls.model_validate(schema)


    @classmethod
    def convert_from_mongo(cls, schema: dict):
        return schema

    @classmethod
    def convert_from_yaml(cls, schema: dict) -> dict:
        return schema


    @classmethod
    def convert_to_mongo(cls, schema: dict):
        return schema

    @classmethod
    def convert_to_yaml(cls, schema: dict) -> dict:
        return schema




    def save(self, db=None, upsert_filter=None):
        """
        Save the current state of the model to the database.
        """
        db = db or self.db or "STAGE"
        
        schema = self.model_dump(by_alias=True, exclude={"db"})
        schema = self.convert_to_mongo(schema)
        schema.pop("_id")
        print("THE SCHEMA AFTER SAVING", schema)
        #self.validate_fields() #???


        filter = upsert_filter or {"_id": self.id}


        self.updated_at = datetime.now(timezone.utc)
        collection = self.get_collection(db)
        if self.id:
            collection.replace_one(filter, schema, upsert=True)
        else:
            self.created_at = datetime.now(timezone.utc)
            result = collection.insert_one(schema)
            self.id = result.inserted_id
        self.db = db

    # todo: this method is probably superfluous, should remove
    def validate_fields(self):
        """
        Validate fields using Pydantic's built-in validation.
        """
        return self.model_validate(self.model_dump())
    





    def update(self, **kwargs):
        """
        Perform granular updates on specific fields.
        """
        updated_data = self.model_copy(update=kwargs)
        updated_data.validate_fields()  # todo: check this, it's probably unnecessary
        collection = self.get_collection(self.db)
        update_result = collection.update_one(
            {"_id": self.id}, 
            {
                "$set": kwargs,
                "$currentDate": {"updated_at": True}
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
                "$currentDate": {"updated_at": True}
            }
        )
        if update_result.modified_count > 0:
            self.updated_at = datetime.now(timezone.utc)

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
            updated_data.validate_fields()
        else:
            raise ValidationError(f"Field '{field_name}' is not a valid list field.")

        # Perform the push operation if validation passes
        collection = self.get_collection(self.db)
        update_result = collection.update_one(
            {"_id": self.id},
            {"$push": {field_name: {"$each": values_to_push}}, "$currentDate": {"updated_at": True}}
        )
        if update_result.modified_count > 0:
            if hasattr(self, field_name) and isinstance(getattr(self, field_name), list):
                setattr(self, field_name, getattr(self, field_name) + values_original)
                self.updated_at = datetime.now(timezone.utc)

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
                updated_data.validate_fields()
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
                "$currentDate": {"updated_at": True}
            }
        )
        if update_result.modified_count > 0:
            # Update the value in the local instance if the update was successful
            if hasattr(self, field_name) and isinstance(getattr(self, field_name), list):
                field_list = getattr(self, field_name)
                if len(field_list) > index and isinstance(field_list[index], dict):
                    field_list[index][sub_field] = value
                    self.updated_at = datetime.now(timezone.utc)

    def reload(self):
        """
        Reload the current document from the database to ensure the instance is up-to-date.
        """
        updated_instance = self.load(self.id, self.db)
        if updated_instance:
            for key, value in updated_instance.dict().items():
                setattr(self, key, value)

    def delete(self):
        """
        Delete the document from the database.
        """
        collection = self.get_collection(self.db)
        collection.delete_one({"_id": self.id})
