import copy
from pydantic import BaseModel, Field, create_model
from typing import Annotated, Any, Optional, Type, List, Dict, Union, get_origin, get_args


class VersionableBaseModel(BaseModel):
    schema: Type[BaseModel]
    initial: BaseModel
    current: BaseModel
    edits: List[BaseModel] = Field(default_factory=list)

    def __init__(self, instance: BaseModel = None, **kwargs):
        if instance is not None:
            data = {
                "schema": type(instance),
                "initial": instance,
                "current": instance
            }
            super().__init__(**data)
        else:
            super().__init__(**kwargs)

    @classmethod
    def load_from5(cls, **kwargs):
        return cls(**kwargs)

    @classmethod
    def model_validate(cls, obj: Any):
        obj['schema'] = recreate_base_model(obj['schema'])
        return super().model_validate(obj)

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        data['schema'] = {
            'name': data['schema'].__name__,
            'schema': data['schema'].model_json_schema()
        }
        data['current'] = self.current.model_dump()
        data['initial'] = self.initial.model_dump()
        data['edits'] = [edit.model_dump() for edit in self.edits]
        return data
    
    def get_edit_model(self) -> Type[BaseModel]:
        return generate_edit_model(self.schema)

    def apply_edit(self, edit: BaseModel):
        self.current = apply_edit(self.current, edit)
        self.edits.append(edit)    

    def reconstruct_version(self, version: int) -> BaseModel:
        if version < 0 or version > len(self.edits):
            raise ValueError("Invalid version number")
        instance = copy.deepcopy(self.initial)
        for edit in self.edits[:version]:
            instance = apply_edit(instance, edit)
        return instance
    

def generate_edit_model(
    model: Type[BaseModel]
) -> Type[BaseModel]:
    """
    Given a Pydantic BaseModel, generate a new BaseModel which represents an edit for that model.
    """

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


def apply_edit(
    instance: BaseModel, 
    edit: BaseModel
) -> BaseModel:
    """
    Given an instance and an edit, apply the edit to the instance.
    """

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

    if instance_copy is None:
        instance_copy = type(edit)()
    elif isinstance(instance_copy, dict):
        instance_copy = type(edit).model_validate(instance_copy)

    return instance_copy.model_copy(update=updates)


def get_python_type(field_info):
    """
    Retrieve the Python type from a field info object.
    """

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


def recreate_base_model(schema: Dict[str, Any]) -> Type[BaseModel]:
    """
    Build a BaseModel from a type model data object.
    """

    model_name = schema['name']
    model_schema = schema['schema']
    base_model = create_model(model_name, **{
        field: (get_python_type(info), ... if info.get('required', False) else None)
        for field, info in model_schema['properties'].items()
    })
    return base_model

