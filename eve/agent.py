from dotenv import load_dotenv
load_dotenv()

import os
import yaml
import copy
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


class Agent(MongoModel):
    key: str
    name: str
    owner: ObjectId
    description: str
    instructions: str
    tools: Optional[List[dict]]

    def __init__(self, env, **data):
        data['description'] = data['description'].strip()
        data['instructions'] = data['instructions'].strip()
        super().__init__(collection_name="agents", env=env, **data)
        #self.get_tools()

    @classmethod
    def from_id(self, document_id: str, env: str):
        return super().from_id(self, document_id, "agents", env)

    def get_system_message(self):
        system_message = f"{self.description}\n\n{self.instructions}\n\n{generic_instructions}"
        return system_message
    
    def get_tools(self):
        tools = copy.deepcopy(self.tools)
        presets = {}
        for tool in tools:
            parent_tool_path = tool.pop('key')
            preset = PresetTool(tool, key=None, parent_tool_path=parent_tool_path)
            presets[preset.key] = preset
        return presets


def load_agent_data(agent_path: str) -> Agent:
    if not os.path.exists(agent_path):
        raise ValueError(f"Agent not found at {agent_path}")
    try:
        data = yaml.safe_load(open(agent_path, "r"))
    except yaml.YAMLError as e:
        raise ValueError(f"Error loading {agent_path}: {e}")
    return data


def update_agent_cli():
    parser = argparse.ArgumentParser(description="Update an agent")
    parser.add_argument('--env', choices=['STAGE', 'PROD'], default='STAGE', help='Environment to run in (STAGE or PROD)')
    parser.add_argument('--agent', help='Name of the agent to update')
    
    args = parser.parse_args()

    try:
        eden_user = os.getenv("EDEN_TEST_USER_PROD") if args.env == "PROD" else os.getenv("EDEN_TEST_USER_STAGE")

        if args.agent:
            agent_files = [f"{args.agent}.yaml"]
        else:
            agent_files = [f for f in os.listdir("agents") if f.endswith(".yaml")]
        
        for agent_file in agent_files:
            agent_key = os.path.splitext(agent_file)[0]
            agent_data = load_agent_data(f"agents/{agent_file}")
            agent = Agent(env=args.env, key=agent_key, owner=ObjectId(eden_user), **agent_data)
            agent.save(upsert_filter={"key": agent.key, "owner": ObjectId(eden_user)})
            print(f"Updated agent on {args.env}: {agent_key}")

    except ValueError as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    update_agent_cli()
