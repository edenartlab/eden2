import os
import yaml
import copy
import json
import traceback
import argparse
from bson import ObjectId
from datetime import datetime, timezone
from abc import ABC
from pydantic import ConfigDict
from typing import Optional, Literal, Any, Dict, List, Union
from eve.thread import UserMessage
from eve.mongo import Document, Collection, get_collection


generic_instructions = """Follow these additional guidelines:
- If the tool you are using has the "n_samples" parameter, and the user requests for multiple versions of the same thing, set n_samples to the number of images the user desires for that prompt. If they want N > 1 images that have different prompts, then make N separate tool calls with n_samples=1.
- When a lora is set, absolutely make sure to include "<concept>" in the prompt to refer to object or person represented by the lora.
- If you get an error using a tool because the user requested an invalid parameter, or omitted a required parameter, ask the user for clarification before trying again. Do *not* try to guess what the user meant.
- If you get an error using a tool because **YOU** made a mistake, do not apologize for the oversight or explain what *you* did wrong, just fix your mistake, and automatically retry the task.
- When returning the final results to the user, do not include *any* text except a markdown link to the image(s) and/or video(s) with the prompt as the text and the media url as the link. DO NOT include any other text, such as the name of the tool used, a summary of the results, the other args, or any other explanations. Just [prompt](url).
- When doing multi-step tasks, present your intermediate results in each message before moving onto the next tool use. For example, if you are asked to create an image and then animate it, make sure to return the image (including the url) to the user (as markdown, like above)."""




# from eve.llm import async_prompt_thread


# todo: consolidate with Tool class
@Collection("agents3")
class Agent(Document, ABC):
    """
    Base class for all agents.
    """

    key: str
    owner: ObjectId

    status: Optional[Literal["inactive", "stage", "prod"]] = "stage"
    visible: Optional[bool] = True
    allowlist: Optional[str] = None

    name: str
    description: str
    instructions: str
    tools: Optional[List[dict]] = None
        
    test_args: Optional[List[Dict[str, Any]]] = None

    @classmethod
    def convert_from_yaml(cls, schema: dict, file_path: str = None) -> dict:
        """
        Convert the schema into the format expected by the model.
        """

        test_file = file_path.replace("api.yaml", "test.json")
        with open(test_file, 'r') as f:
            schema["test_args"] = json.load(f)

        schema['owner'] = ObjectId("669dbb0613310df74fecde1d")
        # owner = schema.get('owner')
        # schema['owner'] = ObjectId(owner) if isinstance(owner, str) else owner         = ObjectId(schema['owner']) if isinstance(schema['owner'], str) else schema.get('owner')

        return schema
    
    def save(self, db=None, **kwargs):
        super().save(db, {"key": self.key}, **kwargs)


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


def get_agents_from_api_files(root_dir: str = None, agents: List[str] = None, include_inactive: bool = False) -> Dict[str, Agent]:
    """Get all agents inside a directory"""
    
    api_files = get_api_files(root_dir, include_inactive)
    
    all_agents = {
        key: Agent.from_yaml(api_file) 
        for key, api_file in api_files.items()
    }

    if agents:
        agents = {k: v for k, v in all_agents.items() if k in agents}
    else:
        agents = all_agents

    return agents

def get_agents_from_mongo(db: str, agents: List[str] = None, include_inactive: bool = False) -> Dict[str, Agent]:
    """Get all agents from mongo"""
    
    filter = {"key": {"$in": agents}} if agents else {}
    agents = {}
    agents_collection = get_collection(Agent.collection_name, db=db)
    for agent in agents_collection.find(filter):
        try:
            agent = Agent.convert_from_mongo(agent)
            agent = Agent.from_schema(agent, db=db)
            if agent.status != "inactive" and not include_inactive:
                if agent.key in agents:
                    raise ValueError(f"Duplicate agent {agent.key} found.")
                agents[agent.key] = agent
        except Exception as e:
            print(traceback.format_exc())
            print(f"Error loading agent {agent['key']}: {e}")

    return agents

def get_api_files(root_dir: str = None, include_inactive: bool = False) -> List[str]:
    """Get all agent directories inside a directory"""
    
    if root_dir:
        root_dirs = [root_dir]
    else:
        eve_root = os.path.dirname(os.path.abspath(__file__))
        root_dirs = [
            os.path.join(eve_root, agents_dir) 
            for agents_dir in ["agents", "../../workflows"]
        ]

    api_files = {}
    for root_dir in root_dirs:
        for root, _, files in os.walk(root_dir):
            if "api.yaml" in files and "test.json" in files:
                api_file = os.path.join(root, "api.yaml")
                with open(api_file, 'r') as f:
                    schema = yaml.safe_load(f)
                if schema.get("status") == "inactive" and not include_inactive:
                    continue
                key = schema.get("key", os.path.relpath(root).split("/")[-1])
                if key in api_files:
                    raise ValueError(f"Duplicate agent {key} found.")
                api_files[key] = os.path.join(os.path.relpath(root), "api.yaml")
            
    return api_files
