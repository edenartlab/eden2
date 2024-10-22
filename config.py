from datetime import datetime
import argparse
import json
import random
import os
from tool import get_tools, get_comfyui_tools
from mongo import get_collection

env = os.getenv("ENV", "STAGE")
if env not in ["PROD", "STAGE"]:
    raise Exception(f"Invalid environment: {env}. Must be PROD or STAGE")

# this controls order of tools in frontend
api_tools = [
    "txt2img", "flux_dev", "flux_schnell", 
    "layer_diffusion", "remix_flux_schnell", "remix", "inpaint", "flux_inpainting", "outpaint", "face_styler", 
    "upscaler", "background_removal", "background_removal_video",
    "animate_3D", "txt2vid", "img2vid", "video_upscaler", "vid2vid_sdxl",
    "texture_flow", "runway",
    "stable_audio", "musicgen",

    # preset tools
    "style_transfer",

    # these are hidden but make them available over API
    "lora_trainer", "flux_trainer", "news", "moodmix", "storydiffusion",
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
    api_tools_order = {tool: index for index, tool in enumerate(api_tools)}
    sorted_tools = sorted(available_tools.items(), 
                          key=lambda x: api_tools_order.get(x[0], len(api_tools)))
    
    for index, (tool_key, tool_config) in enumerate(sorted_tools):
        tool_config = tool_config.get_interface()
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
