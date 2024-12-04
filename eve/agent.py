from dotenv import load_dotenv
load_dotenv()

import os
import yaml
import copy
from datetime import datetime, timezone
import json
import argparse
from .mongo import MongoModel#, mongo_client
from typing import List
from bson import ObjectId
# from .tool import PresetTool

generic_instructions = """Follow these additional guidelines:
- If the tool you are using has the "n_samples" parameter, and the user requests for multiple versions of the same thing, set n_samples to the number of images the user desires for that prompt. If they want N > 1 images that have different prompts, then make N separate tool calls with n_samples=1.
- When a lora is set, absolutely make sure to include "<concept>" in the prompt to refer to object or person represented by the lora.
- If you get an error using a tool because the user requested an invalid parameter, or omitted a required parameter, ask the user for clarification before trying again. Do *not* try to guess what the user meant.
- If you get an error using a tool because **YOU** made a mistake, do not apologize for the oversight or explain what *you* did wrong, just fix your mistake, and automatically retry the task.
- When returning the final results to the user, do not include *any* text except a markdown link to the image(s) and/or video(s) with the prompt as the text and the media url as the link. DO NOT include any other text, such as the name of the tool used, a summary of the results, the other args, or any other explanations. Just [prompt](url).
- When doing multi-step tasks, present your intermediate results in each message before moving onto the next tool use. For example, if you are asked to create an image and then animate it, make sure to return the image (including the url) to the user (as markdown, like above)."""

from typing import Optional



from abc import ABC, abstractmethod
from pydantic import BaseModel, ConfigDict
from typing import Optional, Literal, Any, Dict, List, Union
from eve.thread import UserMessage
from eve.mongo2 import Document, Collection, get_collection


import yaml
# from eve.llm import async_prompt_thread


# todo: consolidate with Tool class
class Agent(BaseModel, ABC):
    """
    Base class for all agents.
    """

    key: str
    owner: ObjectId
    name: str
    description: str
    instructions: str
    tools: Optional[List[dict]] = None
    
    status: Optional[Literal["inactive", "stage", "prod"]] = "stage"
    visible: Optional[bool] = True
    allowlist: Optional[str] = None
    
    test_args: List[Dict[str, Any]]

    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )

    @classmethod
    def load(cls, key: str, db: str = "STAGE", prefer_local: bool = True, **kwargs):
        """Load the tool class based on the handler in api.yaml"""
        
        agents = get_collection("agents", db=db)
        schema = agents.find_one({"key": key})
        
        if not schema:
            raise ValueError(f"Agent with key {key} not found on db: {db}")

        return cls.load_from_schema(schema, prefer_local, **kwargs)

    @classmethod
    def load_from_dir(cls, agent_dir: str, prefer_local: bool = True, **kwargs):
        """Load the tool from an api.yaml and test.json"""
        
        schema = cls._get_schema_from_dir(agent_dir)
        schema['key'] = agent_dir.split('/')[-1]
        
        return cls.load_from_schema(schema, prefer_local, **kwargs)

    @classmethod
    def load_from_schema(cls, schema: dict, prefer_local: bool = True, **kwargs):
        """Load the tool class based on the handler in api.yaml"""
        
        key = schema.pop('key')
        test_args = schema.pop('test_args')
        
        return cls._create_agent(key, schema, test_args, **kwargs)    

    @classmethod
    def _create_agent(cls, key: str, schema: dict, test_args: dict, **kwargs):
        """Create a new tool instance from a schema"""

        agent_data = {k: schema.pop(k) for k in cls.model_fields.keys() if k in schema}
        agent_data['test_args'] = test_args
        agent_data['owner'] = ObjectId(agent_data['owner'])

        return cls(key=key, **agent_data, **kwargs)

    @classmethod
    def _get_schema_from_dir(cls, agent_dir: str):
        if not os.path.exists(agent_dir):
            raise ValueError(f"Agent directory {agent_dir} does not exist")

        api_file = os.path.join(agent_dir, 'api.yaml')
        test_file = os.path.join(agent_dir, 'test.json')

        with open(api_file, 'r') as f:
            schema = yaml.safe_load(f)
                
        with open(test_file, 'r') as f:
            schema['test_args'] = json.load(f)

        return schema
    

    # old code: needs to be reintegrated
    # def get_system_message(self):
    #     system_message = f"{self.description}\n\n{self.instructions}\n\n{generic_instructions}"
    #     return system_message
    
    # def get_tools(self):
    #     tools = copy.deepcopy(self.tools)
    #     presets = {}
    #     for tool in tools:
    #         parent_tool_path = tool.pop('key')
    #         preset = PresetTool(tool, key=None, parent_tool_path=parent_tool_path)
    #         presets[preset.key] = preset
    #     return presets

    # not working yet
    # async def async_prompt(
    #     db: str,
    #     user_id: str, 
    #     thread_name: str,
    #     user_messages: Union[UserMessage, List[UserMessage]], 
    # ):
    #     tools = {} # get self tools
    #     await async_prompt_thread(
    #         db=db,
    #         user_id=user_id,
    #         thread_name=thread_name,
    #         user_messages=user_messages,
    #         tools=tools
    #     )


    async def async_stream(
        db: str,
        user_id: str, 
        thread_name: str,
        user_messages: Union[UserMessage, List[UserMessage]], 
    ):
        pass



def save_agent_from_dir(agent_dir: str, order: int = None, db: str = "STAGE") -> Agent:
    """Upload agents from directory to mongo"""

    schema = Agent._get_schema_from_dir(agent_dir)
    schema['key'] = agent_dir.split('/')[-1]
    
    # timestamps
    agents = get_collection("agents", db=db)
    agent = agents.find_one({"key": schema['key']})
    time = datetime.now(timezone.utc)
    schema['createdAt'] = agent.get('createdAt', time) if agent else time
    schema['updatedAt'] = time
    schema['order'] = order or schema.get('order', len(list(agents.find())))
    schema['owner'] = ObjectId(schema['owner'])
    
    agents.replace_one(
        {"key": schema['key']}, 
        schema,
        upsert=True
    )


def get_agents_from_dirs(root_dir: str = None, agents: List[str] = None, include_inactive: bool = False) -> Dict[str, Agent]:
    """Get all agents inside a directory"""
    
    agent_dirs = get_agent_dirs(root_dir, include_inactive)
    agents = {
        key: Agent.load_from_dir(agent_dir) 
        for key, agent_dir in agent_dirs.items()
        if key in agents
    }

    return agents


def get_agents_from_mongo(db: str, agents: List[str] = None, include_inactive: bool = False, prefer_local: bool = True) -> Dict[str, Agent]:
    """Get all agents from mongo"""
    
    filter = {"key": {"$in": agents}} if agents else {}
    agents = {}
    agents_collection = get_collection("agent", db=db)
    for agent in agents_collection.find(filter):
        try:
            agent = Agent.load_from_schema(agent, prefer_local)
            if agent.status != "inactive" and not include_inactive:
                if agent.key in agents:
                    raise ValueError(f"Duplicate agent {agent.key} found.")
                agents[agent.key] = agent
        except Exception as e:
            print(f"Error loading agent {agent['key']}: {e}")

    return agents


def get_agent_dirs(root_dir: str = None, include_inactive: bool = False) -> List[str]:
    """Get all agent directories inside a directory"""
    
    if root_dir:
        root_dirs = [root_dir]
    else:
        eve_root = os.path.dirname(os.path.abspath(__file__))
        root_dirs = [
            os.path.join(eve_root, agents_dir) 
            for agents_dir in ["agents"]
        ]

    agent_dirs = {}

    for root_dir in root_dirs:
        for root, _, files in os.walk(root_dir):
            if "api.yaml" in files and "test.json" in files:
                api_file = os.path.join(root, "api.yaml")
                with open(api_file, 'r') as f:
                    schema = yaml.safe_load(f)
                if schema.get("status") == "inactive" and not include_inactive:
                    continue
                key = os.path.relpath(root).split("/")[-1]
                if key in agent_dirs:
                    raise ValueError(f"Duplicate agent {key} found.")
                agent_dirs[key] = os.path.relpath(root)
            
    return agent_dirs
