import os
import copy
from abc import abstractmethod
from bson import ObjectId
from datetime import datetime
from pymongo import MongoClient
from pydantic import BaseModel, Field, ConfigDict, create_model
from pydantic_core import core_schema
from pydantic.json_schema import SkipJsonSchema
from typing import Annotated, Any, Optional, Type, List, Dict, Union, get_origin, get_args

from dotenv import load_dotenv
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



# class PydanticObjectId(ObjectId):
#     @classmethod
#     def __get_validators__(cls):
#         yield cls.validate

#     @classmethod
#     def validate(cls, v: Any) -> ObjectId:
#         if isinstance(v, str):
#             return ObjectId(v)
#         if isinstance(v, ObjectId):
#             return v
#         raise ValueError("Invalid ObjectId")

#     @classmethod
#     def __get_pydantic_core_schema__(cls, _source_type: Any, _handler: Any) -> core_schema.CoreSchema:
#         return core_schema.json_or_python_schema(
#             json_schema=core_schema.str_schema(),
#             python_schema=core_schema.union_schema([
#                 core_schema.is_instance_schema(ObjectId),
#                 core_schema.chain_schema([
#                     core_schema.str_schema(),
#                     core_schema.no_info_plain_validator_function(cls.validate)
#                 ])
#             ]),
#             serialization=core_schema.plain_serializer_function_ser_schema(str),
#         )


# PyObjectId = Annotated[
#     PydanticObjectId, 
#     Field(default_factory=PydanticObjectId, alias="_id")
# ]


def generate_edit_model(model: Type[BaseModel]) -> Type[BaseModel]:
    edit_fields: Dict[str, Any] = {}
    model_description = model.__doc__ or ""
    edit_model_description = f"Edit a {model.__name__} ({model_description.strip()})"

    for name, field in model.__annotations__.items():
        origin = get_origin(field)
        args = get_args(field)

        if origin is Union and type(None) in args:
            # Optional[actual_type] found
            actual_type = next(arg for arg in args if arg is not type(None))
            origin = get_origin(actual_type)
            args = get_args(actual_type)

        field_info = model.model_fields[name]
        field_description = field_info.description or ""

        if origin in (list, List):
            item_type = args[0]
            if isinstance(item_type, type) and issubclass(item_type, BaseModel):
                nested_edit_model = generate_edit_model(item_type)
                edit_fields[f'add_{name}'] = (Optional[Dict[str, Union[int, item_type]]], None, f"Add {model.__name__} {name} ({field_description})")
                edit_fields[f'edit_{name}'] = (Optional[Dict[str, Union[int, nested_edit_model]]], None, f"Edit {model.__name__} {name} ({field_description})")
                edit_fields[f'remove_{name}'] = (Optional[int], None, f"Remove {model.__name__} {name} ({field_description})")
            else:
                edit_fields[f'add_{name}'] = (Optional[Dict[str, Union[int, item_type]]], None, f"Add {model.__name__} {name} ({field_description})")
                edit_fields[f'edit_{name}'] = (Optional[Dict[str, Union[int, item_type]]], None, f"Edit {model.__name__} {name} ({field_description})")
                edit_fields[f'remove_{name}'] = (Optional[int], None, f"Remove {model.__name__} {name} ({field_description})")
        elif origin in (dict, Dict):
            key_type, value_type = args
            if isinstance(value_type, type) and issubclass(value_type, BaseModel):
                nested_edit_model = generate_edit_model(value_type)
                edit_fields[f'add_{name}'] = (Optional[Dict[key_type, value_type]], None, f"Add {model.__name__} {name} ({field_description})")
                edit_fields[f'edit_{name}'] = (Optional[Dict[key_type, nested_edit_model]], None, f"Edit {model.__name__} {name} ({field_description})")
                edit_fields[f'remove_{name}'] = (Optional[key_type], None, f"Remove {model.__name__} {name} ({field_description})")
            else:
                edit_fields[f'add_{name}'] = (Optional[Dict[key_type, value_type]], None, f"Add {model.__name__} {name} ({field_description})")
                edit_fields[f'edit_{name}'] = (Optional[Dict[key_type, value_type]], None, f"Edit {model.__name__} {name} ({field_description})")
                edit_fields[f'remove_{name}'] = (Optional[key_type], None, f"Remove {model.__name__} {name} ({field_description})")
        elif isinstance(field, type) and issubclass(field, BaseModel):
            nested_edit_model = generate_edit_model(field)
            edit_fields[f'edit_{name}'] = (Optional[nested_edit_model], None, f"Edit {model.__name__} {name} ({field_description})")
        else:
            edit_fields[f'edit_{name}'] = (Optional[field], None, f"Edit {model.__name__} {name} ({field_description})")
    
    edit_model = create_model(
        f'{model.__name__}Edit',
        **{key: (value[0], Field(default=value[1], description=value[2])) for key, value in edit_fields.items()},
        __base__=BaseModel
    )
    edit_model.__doc__ = edit_model_description

    return edit_model


def apply_edit(instance: BaseModel, edit: BaseModel) -> BaseModel:
    instance_copy = copy.deepcopy(instance)
    updates = {}
    for field_name, value in edit:
        if value is not None:
            if field_name.startswith('add_'):
                original_field = field_name.replace('add_', '')
                if isinstance(value, dict) and 'index' in value:
                    index = value['index']
                    new_value = value['value']
                    if getattr(instance_copy, original_field) is None:
                        setattr(instance_copy, original_field, [])
                    current_list = getattr(instance_copy, original_field)
                    current_list.insert(index, new_value)
                    setattr(instance_copy, original_field, current_list)
                elif isinstance(value, dict):
                    if getattr(instance_copy, original_field) is None:
                        setattr(instance_copy, original_field, {})
                    for key, new_value in value.items():
                        getattr(instance_copy, original_field)[key] = new_value
            elif field_name.startswith('edit_'):
                original_field = field_name.replace('edit_', '')
                if isinstance(value, dict) and 'index' in value and 'value' in value:
                    index = value['index']
                    new_value = value['value']
                    if isinstance(new_value, BaseModel):
                        current_value = getattr(instance_copy, original_field)[index]
                        nested_updated = apply_edit(current_value, new_value)
                        getattr(instance_copy, original_field)[index] = nested_updated
                    else:
                        getattr(instance_copy, original_field)[index] = new_value
                elif isinstance(value, dict):
                    for key, new_value in value.items():
                        if isinstance(new_value, BaseModel):
                            current_value = getattr(instance_copy, original_field)[key]
                            nested_updated = apply_edit(current_value, new_value)
                            getattr(instance_copy, original_field)[key] = nested_updated
                        else:
                            getattr(instance_copy, original_field)[key] = new_value
                elif isinstance(value, BaseModel):
                    nested_instance = getattr(instance_copy, original_field)
                    nested_updated = apply_edit(nested_instance, value)
                    setattr(instance_copy, original_field, nested_updated)
                else:
                    updates[original_field] = value
            elif field_name.startswith('remove_'):
                original_field = field_name.replace('remove_', '')
                if getattr(instance_copy, original_field) is None:
                    continue
                if isinstance(value, int):
                    getattr(instance_copy, original_field).pop(value)
                else:
                    getattr(instance_copy, original_field).pop(value, None)
            else:
                original_field = field_name.replace('edit_', '')
                updates[original_field] = value

    return instance_copy.model_copy(update=updates)


def get_python_type(field_info):
    type_map = {
        'string': str,
        'integer': int,
        'number': float,
        'boolean': bool,
        'array': List,
        'object': Dict
    }
    field_type = field_info.get('type')
    if field_type == 'array' and 'items' in field_info:
        item_type = get_python_type(field_info['items'])
        return List[item_type]
    if field_type == 'object':
        return Dict[str, Any]
    return type_map.get(field_type, Any)


def recreate_base_model(type_model_data: Dict[str, Any]) -> Type[BaseModel]:
    model_name = type_model_data['name']
    model_schema = type_model_data['schema']
    base_model = create_model(model_name, **{
        field: (get_python_type(info), ... if info.get('required', False) else None)
        for field, info in model_schema['properties'].items()
    })
    return base_model


class MongoModel(BaseModel):
    # id: PyObjectId
    id: Annotated[ObjectId, Field(default_factory=ObjectId, alias="_id")]
    # collection: ClassVar[SkipJsonSchema[Collection]] = None
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

    # @classmethod
    # def model_validate(cls, obj: Any):
    #     if isinstance(obj, dict) and 'type_model' in obj and isinstance(obj['type_model'], dict):
    #         obj['type_model'] = recreate_base_model(obj['type_model'])
    #     return super().model_validate(obj)

    def save(self):
        self.model_validate({**self.model_dump(), **{"env": self.env}})
        data = self.model_dump(by_alias=True, exclude_none=True)
        data['_id'] = ObjectId(data['_id'])
        # collection = get_collection(self.get_collection_name(), self.env)
        # document = collection.find_one({"_id": data['_id']})
        # if document:
        #     collection.update_one({"_id": data['_id']}, {"$set": data})
        # else:
        #     collection.insert_one(data)
    
    @classmethod
    def load(cls, document_id: str, env: str):
        collection = get_collection(cls.get_collection_name(), env)
        document = collection.find_one({"_id": ObjectId(document_id)})
        document['env'] = env
        return cls.model_validate(document)

    def update(self, **kwargs):
        update_args = {}
        for key, value in kwargs.items():
            if hasattr(self, key) and getattr(self, key) != value:
                setattr(self, key, value)
                update_args[key] = value
        if not update_args:
            return self
        self.model_validate({**self.model_dump(), **update_args, **{"env": self.env}})
        current_time = datetime.utcnow().replace(microsecond=0)
        self.updatedAt = current_time
        update_args['updatedAt'] = self.updatedAt
        # get_collection(self.get_collection_name(), self.env).update_one(
        #     {"_id": ObjectId(self.id)},
        #     {"$set": update_args}
        # )








class Task(MongoModel):
    workflow: str
    num: int = Field(ge=1, le=10, default=1)
    args: Dict[str, Any]
    user: ObjectId

    @classmethod
    def get_collection_name(cls) -> str:
        return "stories"


class VersionableMongoModel(MongoModel):
    type_model: Type[BaseModel]
    current: BaseModel
    edits: List[BaseModel] = Field(default_factory=list)
    collection_name: SkipJsonSchema[str] = Field(None, exclude=True)

    def __init__(self, **data):
        data["current"] = data["type_model"]()
        super().__init__(**data)

    @classmethod
    def model_validate(cls, obj: Any):
        obj['type_model'] = recreate_base_model(obj['type_model'])
        return super().model_validate(obj)

    def get_collection_name(self) -> str:
        return self.collection_name

    @classmethod
    def load(cls, document_id: str, collection_name: str, env: str):
        collection = get_collection(collection_name, env)
        document = collection.find_one({"_id": ObjectId(document_id)})
        if document is None:
            raise ValueError(f"Document with id {document_id} not found in collection {collection_name}")
        document['type_model'] = recreate_base_model(document['type_model'])
        return cls(env=env, collection_name=collection_name, **document)

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        if True: #'type_model' in data:
            data['type_model'] = {
                'name': data['type_model'].__name__,
                'schema': data['type_model'].model_json_schema()
            }
        if True: #'current' in data:
            data['current'] = self.current.model_dump()
        if True: #'edits' in data:
            data['edits'] = [edit.model_dump() for edit in self.edits]
        # data['current'] = data['current'].model_dump()
        return data
    
    def get_edit_model(self) -> Type[BaseModel]:
        return generate_edit_model(self.type_model)

    def apply_edit(self, edit: BaseModel):
        self.current = apply_edit(self.current, edit)
        self.edits.append(edit)
        self.save()

    def reconstruct_version(self, version: int) -> BaseModel:
        if version < 0 or version > len(self.edits):
            raise ValueError("Invalid version number")
        instance = self.type_model()
        for edit in self.edits[:version]:
            instance = apply_edit(instance, edit)
        return instance
    
    def save(self):
        self.model_validate({**self.model_dump(), **{"env": self.env}})
        doc = self.model_dump(by_alias=True, exclude_none=True)
        doc['_id'] = ObjectId(doc['_id'])
        collection = get_collection(self.get_collection_name(), self.env)
        document = collection.find_one({"_id": doc['_id']})
        if document:
            collection.update_one({"_id": doc['_id']}, {"$set": doc})
        else:
            collection.insert_one(doc)
            












# t = Task(env="STAGE", workflow="1202034124", args={"test": "212122"}, user=ObjectId("666666663333366666666666"))
# t.save()
# print(t.id)



# t = Task.load("6709caad8eaf77aa8a8f8a0b", env="STAGE")
# print(t)
# t = t.update(blah="dsfs", num=9, workflow="ok 222 the new one 999", args={"hellonew_arg": "3456345345"})


# raise Exception("stop")


# from base2 import generate_edit_model, apply_edit



class Agent2(BaseModel):
    """
    A character with all its info.
    """
    name: Optional[str] = Field(None, description="The character's name")
    description: Optional[str] = Field(None, description="The character's description")
    attributes: Optional[List[str]] = Field(None, description="The character's attributes")




# # # Usage example:
# # print("ok1")
# agent = VersionableMongoModel(type_model=Agent2, collection_name="agents", env="STAGE")
# print("ok2")
# agent.save()
# print("ok3")



# AgentEdit = agent.get_edit_model()

# agent.apply_edit(
#     AgentEdit(
#         edit_name="Bob",
#         edit_description="Go Alice!",
#         add_attributes={"index": 0, "value": "abc"}
#     )
# )



# agent.apply_edit(
#     AgentEdit(
#         edit_name="May",
#         edit_description="no no!",
#         add_attributes={"index": 0, "value": "123"}
#     )
# )


# agent.apply_edit(
#     AgentEdit(
#         edit_description="no no!",
#         add_attributes={"index": 2, "value": "def"}
#     )
# )

# agent.apply_edit(
#     AgentEdit(
#         edit_attributes={"index": 0, "value": "012345"}
#     )
# )



# agent.save()


# p(AgentEdit.model_json_schema())



# a = VersionableMongoModel.load("6709dd6a2a5607571453b9e8", collection_name="agents", env="STAGE")
# print("ok4")
# print(a)





