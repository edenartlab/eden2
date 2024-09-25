import os
from tool import get_tools, get_comfyui_tools

env = os.getenv("ENV", "STAGE")
if env not in ["PROD", "STAGE"]:
    raise Exception(f"Invalid environment: {env}. Must be PROD or STAGE")

api_tools = [
    "txt2img", "flux-dev", "flux-schnell", 
    "img2img", "controlnet", "layer_diffusion", 
    "remix", "inpaint", "outpaint", "face_styler", "storydiffusion",
    "upscaler", "background_removal", "background_removal_video",     
    "animate_3D", "style_mixing", "txt2vid", "vid2vid_sdxl", "img2vid", "video_upscaler", 
    "reel", "story",
    "stable_audio", "audiocraft",
    "lora_trainer", "news", "moodmix",
    "xhibit_vton", "xhibit_remix", "beeple_ai",
]
available_tools = get_comfyui_tools("../workflows/workspaces")
available_tools.update(get_comfyui_tools("../private_workflows/workspaces"))
available_tools.update(get_tools("tools"))
available_tools.update(get_tools("writing_tools"))
if env == "PROD":
    available_tools = {k: v for k, v in available_tools.items() if k in api_tools}
