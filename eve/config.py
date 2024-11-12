"""
import argparse
import json
import random
import os
from tool import *
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


"""
TODO
- env: local (yaml), stage, prod
- get_tools(env=local, env=stage, env=prod)
- test_tools, test_api, test_sdk adapt
"""


def get_all_tools_from_yaml():
    tools = get_comfyui_tools("../workflows/workspaces")
    tools.update(get_comfyui_tools("../private_workflows/workspaces"))
    tools.update(get_tools("tools"))
    tools.update(get_tools("tools/media_utils"))
    return tools


def get_all_tools_from_mongo():
    tools_collection = get_collection("tools", env)
    tools = {}
    for tool in tools_collection.find():
        key = tool.pop("key")
        print("KEY", key)
        tool['cost_estimate'] = tool.pop('costEstimate')
        tool['output_type'] = tool.pop('outputType')
        tool['base_model'] = tool.pop('baseModel', None)
        if tool.get('parent_tool'):
            data = yaml.safe_load(open(f"tools/{key}/api.yaml", "r"))
            if data.get('cost_estimate'):
                data['cost_estimate'] = str(data['cost_estimate'])
            workspace = data.pop('parent_tool')
            data['workspace'] = workspace
            tools[key] = PresetTool(data, key=key, parent_tool_path=workspace)
        elif tool["handler"] == "comfyui":
            tools[key] = ComfyUITool(tool, key)
        elif tool["handler"] == "replicate":
            tools[key] = ReplicateTool(tool, key)
        elif tool["handler"] == "gcp":
            tools[key] = GCPTool(tool, key)
        else:
            tools[key] = ModalTool(tool, key)

    return tools


# available_tools = get_all_tools()
# if env == "PROD":
#     available_tools = {k: v for k, v in available_tools.items() if k in ordered_tools}


def update_tools():
    parser = argparse.ArgumentParser(description="Upload arguments")
    parser.add_argument('--env', choices=['STAGE', 'PROD'], default='STAGE', help='Environment to run in (STAGE or PROD)')
    parser.add_argument('--tools', nargs='+', help='List of tools to update')
    args = parser.parse_args()

    available_tools = get_all_tools_from_yaml()

    print(available_tools.keys())

    if args.tools:
        available_tools = {k: v for k, v in available_tools.items() if k in args.tools}

    tools_collection = get_collection("tools", args.env)
    api_tools_order = {tool: index for index, tool in enumerate(ordered_tools)}
    sorted_tools = sorted(available_tools.items(), 
                          key=lambda x: api_tools_order.get(x[0], len(ordered_tools)))
    
    for index, (tool_key, tool) in enumerate(sorted_tools):
        tool_config = tool.model_dump()


        # temporary until visible activated
        tool_config['private'] = not tool_config.pop('visible', True)


        tool_config['costEstimate'] = tool_config.pop('cost_estimate')
        tool_config['outputType'] = tool_config.pop('output_type')
        if 'base_model' in tool_config:
            tool_config['baseModel'] = tool_config.pop('base_model')
        if 'parent_tool' in tool_config:
            tool_config.pop('parent_tool')
            tool_config['parent_tool'] = tool.parent_tool.model_dump()
        tool_config["updatedAt"] = datetime.utcnow()
        
        if not args.tools:
            tool_config['order'] = index  # set order based on the new sorting
        
        existing_doc = tools_collection.find_one({"key": tool_key})        
        update_operation = {
            "$set": tool_config,
            "$setOnInsert": {"createdAt": datetime.utcnow()},
            "$unset": {k: "" for k in (existing_doc or {}) if k not in tool_config and k != "createdAt" and k != "_id"}
        }        
        tools_collection.update_one(
            {"key": tool_key},
            update_operation,
            upsert=True
        )
        
        parameters = ", ".join([p["name"] for p in tool_config.pop("parameters")])
        print(f"\033[38;5;{random.randint(1, 255)}m")
        print(f"\n\nUpdated {args.env} {tool_key}\n============")
        tool_config.pop("updatedAt")
        print(json.dumps(tool_config, indent=2))
        print(f"Parameters: {parameters}")
    
    print(f"\033[97m \n\n\nUpdated {len(available_tools)} tools : {', '.join(available_tools.keys())}")
        

if __name__ == "__main__":
    update_tools()
<<<<<<< HEAD

"""

from datetime import datetime
from pprint import pprint
import asyncio
import argparse
import os
import requests

import eden_utils
# from tool import get_tools_from_dir, get_tools_from_mongo

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
# from tool import get_tools_from_dir, get_tools_from_mongo
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
# tool_dir = "tools/style_transfer"

import tool

tool_dirs = tool._get_tool_dirs()
print(tool_dirs)

flux = tool.load_tool_from_dir(tool_dir=tool_dirs['flux_dev'])
print(flux)

tool.save_tool(tool_dir, env="STAGE")

# from tool import Tool

# # flux2 = Tool.from_mongo(env="STAGE", key="flux_dev")


# #flux2 = tool.load_tool_from_mongo(key="flux_dev", env="STAGE")
# flux2 = tool.load_tool_from_mongo(key="style_transfer", env="STAGE")



# t1 = tool.get_tools_from_dir("tools", env="STAGE")
# t2 = tool.get_tools_from_mongo("STAGE")



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
=======
>>>>>>> abd66b1fafce84c83ecd41a1f4312cbd1a70982d
