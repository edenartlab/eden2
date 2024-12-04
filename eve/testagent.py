# from eve.agent import Agent
# agent = Agent.load_from_dir("eve/agents/eve")
# agent2 = Agent.load("eve")
# import json
# from pprint import pprint
# pprint(agent.model_dump())
# pprint(agent2.model_dump())
# print(agent2.id)


from typing import List, Dict, Any, Optional, Literal, Type
from pydantic import BaseModel, create_model
from eve.mongo3 import Document, Collection, Field

from eve.base import parse_schema
from eve import eden_utils


"""
load from mongo
 - convert params, cost_estimate, etc
load from yaml


save to mongo
save to yaml

"""



@Collection("testgene")
class Tool(Document):
    """
    Base class for all tools.
    """

    key: str
    name: str
    description: str
    tip: Optional[str] = None
    
    output_type: Literal["boolean", "string", "integer", "float", "image", "video", "audio", "lora"]
    cost_estimate: str
    resolutions: Optional[List[str]] = None
    base_model: Literal["sd15", "sdxl", "sd3", "flux-dev", "flux-schnell"] = "sdxl"
    
    status: Optional[Literal["inactive", "stage", "prod"]] = "stage"
    visible: Optional[bool] = True
    allowlist: Optional[str] = None
    
    model: Type[BaseModel] #= None  # should this be optional?
    handler: Literal["local", "modal", "comfyui", "replicate", "gcp"] = "local"
    parent_tool: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    parameter_presets: Optional[Dict[str, Any]] = None
    gpu: Optional[str] = None    
    tests: Optional[List[Dict[str, Any]]] = None


    @classmethod
    def convert_from_mongo(cls, schema: dict) -> dict:
        schema["parameters"] = {
            p["name"]: {**(p.pop("schema")), **p} for p in schema["parameters"]
        }

        fields, model_config = parse_schema(schema)
        model = create_model(schema["key"], __config__=model_config, **fields)    
        model.__doc__ = eden_utils.concat_sentences(schema.get('description'), schema.get('tip', ''))
        schema["model"] = model
        
        if 'cost_estimate' in schema:
            schema['cost_estimate'] = str(schema['cost_estimate'])
                
        return schema

    @classmethod
    def convert_to_mongo(cls, schema: dict) -> dict:
        parameters = []
        for k, v in schema["parameters"].items():
            v['schema'] = {
                key: v.pop(key) 
                for key in ['type', 'items', 'anyOf']
                if key in v
            }
            parameters.append({"name": k, **v})

        schema["parameters"] = parameters
        schema.pop("model")
        
        return schema

    @classmethod
    def convert_from_yaml(cls, schema: dict) -> dict:
        """
        Convert the schema into the format expected by the model.
        """
        
        fields, model_config = parse_schema(schema)
        model = create_model(schema["key"], __config__=model_config, **fields)    
        model.__doc__ = eden_utils.concat_sentences(schema.get('description'), schema.get('tip', ''))
        schema["model"] = model

        return schema

    def save(self, db=None):
        super().save(db, {"key": self.key})







# tool = Tool(
#     key="testgene", 
#     name="Test Gene", 
#     description="Test Gene", 
#     output_type="image", 
#     cost_estimate="10", 
#     test_args={"prompt": "a beautiful image"}, 
#     parameters=[
#         {"name": "prompt", "type": "string", "default": "a beautiful image"},
#         {"name": "negative_prompt", "type": "string", "default": "a beautiful image"}
#     ],
#     model=None, 
#     handler="local"
# )
# tool.save(db="STAGE")



# tool = Tool.from_yaml("eve/testagent.yaml")


tool = Tool.from_yaml("eve/tools/runway/api.yaml")



tool.save(db="STAGE")

tool2 = Tool.from_mongo("6750c50679e00297cd4c603f", "STAGE")
tool2.save(db="STAGE")

print("----")
print(tool)

tool3 = Tool.from_mongo("6750c50679e00297cd4c603f", "STAGE")
print(tool3)


