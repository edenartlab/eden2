"""
import argparse
import json
import random
import os
from tool import get_tools, get_comfyui_tools
from mongo import get_collection

env = os.getenv("ENV", "STAGE")
if env not in ["PROD", "STAGE"]:
    raise Exception(f"Invalid environment: {env}. Must be PROD or STAGE")

api_tools = [
    "txt2img", "flux_dev", "flux_schnell", 
    "img2img", "controlnet", "layer_diffusion", 
    "remix", "inpaint", "outpaint", "face_styler", "storydiffusion",
    "upscaler", "background_removal", "background_removal_video",     
    "animate_3D", "style_mixing", "txt2vid", "vid2vid_sdxl", "img2vid", "video_upscaler", 
    "reel", "story", "texture_flow", "runway",
    "stable_audio", "musicgen",
    "lora_trainer", "flux_trainer", "news", "moodmix",
    "xhibit_vton", "xhibit_remix", "beeple_ai",
]

def get_all_tools():
    tools = get_comfyui_tools("../workflows/workspaces")
    tools.update(get_comfyui_tools("../private_workflows/workspaces"))
    tools.update(get_tools("tools"))
    return tools


available_tools = get_all_tools()
if env == "PROD":
    available_tools = {k: v for k, v in available_tools.items() if k in api_tools}


def update_tools():
    parser = argparse.ArgumentParser(description="Upload arguments")
    parser.add_argument('--env', choices=['STAGE', 'PROD'], default='STAGE', help='Environment to run in (STAGE or PROD)')
    parser.add_argument('--tools', nargs='+', help='List of tools to update')
    args = parser.parse_args()

    available_tools = get_all_tools()

    if args.tools:
        available_tools = {k: v for k, v in available_tools.items() if k in args.tools}

    if args.env == "PROD":
        available_tools = {k: v for k, v in available_tools.items() if k in api_tools}

    tools_collection = get_collection("tools", args.env)
    for tool_key, tool_config in available_tools.items():
        tool_config = tool_config.get_interface()
        tools_collection.update_one(
            {"key": tool_key},
            {
                "$set": tool_config, 
                "$unset": {k: "" for k in tools_collection.find_one({"key": tool_key}, {"_id": 0}) or {} if k not in tool_config}
            },
            upsert=True
        )
        parameters = ", ".join([p["name"] for p in tool_config.pop("parameters")])
        print(f"\033[38;5;{random.randint(1, 255)}m")
        print(f"\n\nUpdated {args.env} {tool_key}\n============")
        print(json.dumps(tool_config, indent=2))
        print(f"Parameters: {parameters}")
    
    print(f"\033[97m \n\n\nUpdated {len(available_tools)} tools : {', '.join(available_tools.keys())}")
        

if __name__ == "__main__":
    update_tools()

"""

from datetime import datetime
from pprint import pprint
import asyncio
import argparse
import os
import requests

import eden_utils
from tool import get_tools_from_dir, get_tools_from_mongo

parser = argparse.ArgumentParser(description="Save tools to mongo")
parser.add_argument("--tools", type=str, nargs='+', help="Which tools to save (space-separated)", default=None)
parser.add_argument("--env", help="Save results to a folder")
args = parser.parse_args()

async def upload_tool(tool):
    print("--------------------------------")
    print(tool)
        
async def run_all_tests():
    tools = get_tools_from_dir("tools")
    tools.update(get_tools_from_dir("../../workflows"))
    # tools.update(get_tools("../../private_workflows"))
    if args.tools:
        tools = {k: v for k, v in tools.items() if k in args.tools}
    print(f"Saving tools: {', '.join(tools.keys())}")
    results = await asyncio.gather(*[upload_tool(tool) for tool in tools.values()])
    return results

# if __name__ == "__main__":
#     asyncio.run(run_all_tests())



from base import parse_schema
from tool import get_tools_from_dir, get_tools_from_mongo
import yaml
import json

# schema = yaml.safe_load(open("../../workflows/workspaces/flux/workflows/flux_dev/api.yaml", "r").read())
# pprint(parse_schema(schema))





# tools = get_tools("../../workflows")

# flux = tools["flux_dev"]

# # print(flux)

import os
import yaml
# flux.save()
from tool import load_tool_from_dir, load_tool_from_mongo


tool_dir = "../../workflows/workspaces/flux/workflows/flux_dev"
tool_dir = "tools/flux_schnell"

"""
import tool

flux = tool.load_tool_from_dir(tool_dir=tool_dir, env="STAGE")


tool.save_tool(tool_dir, env="STAGE")

from tool import Tool

# flux2 = Tool.from_mongo(env="STAGE", key="flux_dev")


#flux2 = tool.load_tool_from_mongo(key="flux_dev", env="STAGE")
flux2 = tool.load_tool_from_mongo(key="flux_schnell", env="STAGE")



t1 = tool.get_tools_from_dir("tools", env="STAGE")
t2 = tool.get_tools_from_mongo("STAGE")
"""



# tool = load_tool_from_dir("tools/style_transfer", env="STAGE")

# all_tools = get_tools_from_dir("tools", env="STAGE")
# print(all_tools)

# print(all_tools["style_transfer"])


# tool = load_tool(tool_dir)

# api_file = os.path.join(tool_dir, 'api.yaml')
# with open(api_file, 'r') as f:
#     schema = yaml.safe_load(f)

# import json
# print(json.dumps(schema, indent=2))




# from mongo import get_collection
# collection = get_collection("tools2", env="STAGE")
# collection.insert_one(schema)
