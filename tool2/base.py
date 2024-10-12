import yaml
from pydantic import BaseModel, Field, create_model
from typing import List, Dict, Any, Union
from enum import Enum
from instructor.function_calls import openai_schema

def get_type(type_str: str):
    type_mapping = {
        'str': str,
        'int': int,
        'float': float,
        'bool': bool,
        'array': List,
        'object': Dict[str, Any]
    }
    return type_mapping.get(type_str, Any)

def create_enum(name: str, choices: List[str]):
    return Enum(name, {choice: choice for choice in choices})

def parse_schema(schema: dict):
    fields = {}
    for field, props in schema.get('properties', {}).items():
        field_kwargs = {}
        
        if 'description' in props:
            field_kwargs['description'] = props['description']
        if 'example' in props:
            field_kwargs['example'] = props['example']
        
        # Store additional properties
        additional_props = {}
        if 'label' in props:
            additional_props['label'] = props['label']
        if 'required' in props:
            additional_props['required'] = props['required']
        
        # Handle min and max for int and float
        if props['type'] in ['int', 'float']:
            if 'minimum' in props:
                field_kwargs['ge'] = props['minimum']
            if 'maximum' in props:
                field_kwargs['le'] = props['maximum']
        
        # Handle enum for strings
        if props['type'] == 'str' and 'enum' in props:
            enum_type = create_enum(f"{field.capitalize()}Enum", props['enum'])
            fields[field] = (enum_type, Field(**field_kwargs, **additional_props))
            continue
        
        if props['type'] == 'object':
            nested_model = create_model(field, **parse_schema(props))
            fields[field] = (nested_model, Field(**field_kwargs, **additional_props))
        elif props['type'] == 'array':
            item_type = get_type(props['items']['type'])
            if props['items']['type'] == 'object':
                item_type = create_model(f"{field}Item", **parse_schema(props['items']))
            fields[field] = (List[item_type], Field(**field_kwargs, **additional_props))
        else:
            fields[field] = (get_type(props['type']), Field(**field_kwargs, **additional_props))
    
    return fields

def model_from_yaml(yaml_file: str):
    with open(yaml_file, 'r') as f:
        schema = yaml.safe_load(f)
    
    fields = parse_schema(schema['person'])
    return create_model('PersonModel', **fields)

# YAML File Content with descriptions, examples, min/max, and enum
yaml_data = """
person:
  type: object
  description: "This model represents a person with their details like name, age, hobbies, contacts, and address."
  properties:
    name:
      type: "str"
      description: "The person's name"
      example: "John"
      label: "Full Name"
      required: true
      enum: ["John", "Jane", "Alice", "Bob"]
    age:
      type: "int"
      description: "The person's age"
      example: 30
      label: "Age"
      required: false
      minimum: 0
      maximum: 120
    height:
      type: "float"
      description: "The person's height in meters"
      example: 1.75
      minimum: 0.5
      maximum: 2.5
    hobbies:
      type: "array"
      items:
        type: "str"
      description: "List of hobbies"
      example: ["reading", "swimming", "coding"]
    contacts:
      type: "array"
      items:
        type: object
        properties:
          type:
            type: "str"
            description: "The contact method type"
            example: "email"
            enum: ["email", "phone", "social_media"]
          value:
            type: "str"
            description: "The contact value"
            example: "john@example.com"
      description: "A list of contact methods"
      example: [{"type": "email", "value": "john@example.com"}, {"type": "phone", "value": "123456789"}]
    address:
      type: object
      properties:
        street:
          type: "str"
          description: "The street address"
          example: "123 Main St"
        city:
          type: "str"
          description: "The city name"
          example: "Somewhere"
        postal_code:
          type: "int"
          description: "Postal code for the address"
          example: 12345
          minimum: 10000
          maximum: 99999
      description: "The person's address"
      example: {"street": "123 Main St", "city": "Somewhere", "postal_code": 12345}
    matrix:
      type: object
      properties:
        data:
          type: "array"
          items:
            type: "array"
            items:
              type: "int"
          description: "A row in the matrix"
      description: "A 2D array of integers (matrix)"
      example: {"data": [[1, 2, 3], [4, 5, 6], [7, 8, 9]]}
"""

# Write the YAML to a file
with open('schema.yaml', 'w') as f:
    f.write(yaml_data)

# Generate the dynamic Pydantic model
PersonModel = model_from_yaml('schema.yaml')

# Example usage
person_instance = PersonModel(
    name="John",
    age=30,
    height=1.75,
    hobbies=["swimming", "reading", "coding"],
    contacts=[
        {"type": "email", "value": "john@example.com"},
        {"type": "phone", "value": "123456789"}
    ],
    address={"street": "123 Main St", "city": "Somewhere", "postal_code": 12345},
    matrix={"data": [[1, 2, 3], [4, 5, 6], [7, 8, 9]]}
)

print(person_instance)

schema = openai_schema(PersonModel).openai_schema

print(schema)



