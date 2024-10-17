from dotenv import load_dotenv
load_dotenv()

import os
import yaml
import json
import argparse
from mongo import MongoBaseModel#, mongo_client
from typing import List
from bson import ObjectId


generic_instructions = """Follow these additional guidelines:
- If the tool you are using has the "n_samples" parameter, and the user requests for multiple versions of the same thing, set n_samples to the number of images the user desires for that prompt. If they want N > 1 images that have different prompts, then make N separate tool calls with n_samples=1.
- When a lora is set, absolutely make sure to include "<concept>" in the prompt to refer to object or person represented by the lora.
- If you get an error using a tool because the user requested an invalid parameter, or omitted a required parameter, ask the user for clarification before trying again. Do *not* try to guess what the user meant.
- If you get an error using a tool because **YOU** made a mistake, do not apologize for the oversight or explain what *you* did wrong, just fix your mistake, and automatically retry the task.
- When returning the final results to the user, do not include *any* text except a markdown link to the image(s) and/or video(s) with the prompt as the text and the media url as the link. DO NOT include any other text, such as the name of the tool used, a summary of the results, the other args, or any other explanations. Just [prompt](url).
- When doing multi-step tasks, present your intermediate results in each message before moving onto the next tool use. For example, if you are asked to create an image and then animate it, make sure to return the image (including the url) to the user (as markdown, like above)."""



class Agent(MongoBaseModel):
    key: str
    name: str
    owner: ObjectId
    description: str
    instructions: str
    tools: List[str]

    def __init__(self, env, **data):
        data['description'] = data['description'].strip()
        data['instructions'] = data['instructions'].strip()
        super().__init__(collection_name="agents", env=env, **data)

    @classmethod
    def from_id(self, document_id: str, env: str):
        return super().from_id(self, document_id, "agents", env)

    def get_system_message(self):
        system_message = f"{self.description}\n\n{self.instructions}\n\n{generic_instructions}"
        return system_message


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
    parser.add_argument('--agent', required=True, help='Name of the agent to update')
    
    args = parser.parse_args()
    print(args)

    try:
        eden_user = os.getenv("EDEN_TEST_USER_PROD") if args.env == "PROD" else os.getenv("EDEN_TEST_USER_STAGE")
        agent = load_agent_data(f"agents/{args.agent}.yaml")
        agent = Agent(env=args.env, key=args.agent, owner=ObjectId(eden_user), **agent)
        agent.save(upsert_query={"key": agent.key, "owner": ObjectId(eden_user)})
    except ValueError as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    update_agent_cli()








