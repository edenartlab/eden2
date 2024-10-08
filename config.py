import argparse
import os
from tool import get_tools, get_comfyui_tools
from mongo import get_collection

env = os.getenv("ENV", "STAGE")
if env not in ["PROD", "STAGE"]:
    raise Exception(f"Invalid environment: {env}. Must be PROD or STAGE")

api_tools = [
    "txt2img", "flux-dev", "flux-schnell", 
    "img2img", "controlnet", "layer_diffusion", 
    "remix", "inpaint", "outpaint", "face_styler", "storydiffusion",
    "upscaler", "background_removal", "background_removal_video",     
    "animate_3D", "style_mixing", "txt2vid", "vid2vid_sdxl", "img2vid", "video_upscaler", 
    "reel", "story", "TextureFlow", "runway",
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
    args = parser.parse_args()

    available_tools = get_all_tools()
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

    # print(f"Environment: {env}")
    # print(f"Available tools: {list(available_tools.keys())}")

if __name__ == "__main__":
    update_tools()