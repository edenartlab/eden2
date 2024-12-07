import os
import copy
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


class Document(BaseModel):
    id: Optional[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    createdAt: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: Optional[datetime] = None
    db: Optional[str] = None  # The name of the database to save to, not saved in MongoDB

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
    def load(cls, document_id: ObjectId, db="STAGE"):
        """
        Load the document from the database and return an instance of the model.
        """
        document_id = document_id if isinstance(document_id, ObjectId) else ObjectId(document_id)
        data = cls.get_collection(db).find_one({"_id": document_id})
        # if data:
        #     instance = cls.model_validate(data)
        #     instance.db = db
        #     return instance
        # return None
        if not data:
            raise ValueError(f"Document {document_id} not found in {cls.collection_name}:{db}")
        
        instance = cls.model_validate(data)
        instance.db = db
        return instance
        

    def save(self, db=None):
        """
        Save the current state of the model to the database.
        """
        db = db or self.db or "STAGE"
        self.validate_fields()
        self.updatedAt = datetime.now(timezone.utc)
        collection = self.get_collection(db)
        if self.id:
            collection.replace_one({"_id": self.id}, self.dict(by_alias=True, exclude={"db"}), upsert=True)
        else:
            self.createdAt = datetime.now(timezone.utc)
            result = collection.insert_one(self.dict(by_alias=True, exclude={"db"}))
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
            updated_data.validate_fields()
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


# Example Usage
@Collection("my_users")
class User(Document):
    username: str
    email: str
    is_active: bool
    roles: List[Dict[str, Any]]
    preferences: Dict[str, str]
    age: int = Field(..., ge=18, le=99)  # New variable with minimum and maximum constraint

# # Create a new user and save it to MongoDB
# user = User(username="john_doe", email="john@example.com", is_active=True, roles=[{"role": {"user": "bill", "shift": 2}}, {"role": {"admin": "alice", "age": 40}}], preferences={"theme": "dark", "language": "en"}, age=30)
# user.save(db="STAGE")

# # Load user from MongoDB
# loaded_user = User.load(user.id, db="STAGE")
# print(loaded_user)

# # Update user information with valid age
# to_update = {"email": "john_doe_updated@example.com", "is_active": False, "age": 25}
# loaded_user.update(db="STAGE", **to_update)
# print(loaded_user)

# # Push a new role to the roles array
# loaded_user.push("roles", {"role": {"editor": "jeff", "shift": 3}}, db="STAGE")
# print(loaded_user)

# # Update a nested field within the roles array
# loaded_user.update_nested_field("roles", 1, "role", {"director": "yokel", "age": 45}, db="STAGE")
# print(loaded_user)

# # Reload the user from MongoDB to get any external changes
# loaded_user.reload(db="STAGE")
# print(loaded_user)

# # Attempt to update user information with invalid age (should fail)
# to_update_invalid = {"age": 120}
# loaded_user.update(db="STAGE", **to_update_invalid)

# # Delete user from MongoDB
# # loaded_user.delete(db="STAGE")





class VersionableMongoModel(VersionableBaseModel):
    id: Annotated[ObjectId, Field(default_factory=ObjectId, alias="_id")]
    collection_name: SkipJsonSchema[str] = Field(..., exclude=True)
    env: SkipJsonSchema[str] = Field(..., exclude=True)
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
        
        edits = [
            generate_edit_model(schema)(**edit) 
            for edit in document['edits']
        ]
        
        versionable_data = {
            "id": document['_id'],
            "collection_name": collection_name, 
            "env": env,
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
        collection = get_collection(self.collection_name, self.env)

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
