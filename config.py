import os
from tool import get_tools, get_comfyui_tools

env = os.getenv("ENV", "STAGE")
if env not in ["PROD", "STAGE"]:
    raise Exception(f"Invalid environment: {env}. Must be PROD or STAGE")

prod_tools = [
    "txt2img", "img2img", "controlnet", "layer_diffusion", 
    "remix", "inpaint", "outpaint", "storydiffusion", "face_styler", "upscaler",
    "background_removal", "background_removal_video",     
    "flux-dev", "flux-schnell", 
    "animate_3D", "txt2vid", "img2vid", "vid2vid_sdxl", "style_mixing", "video_upscaler", 
    "stable_audio", "audiocraft", "reel",
    "lora_trainer", "news", "moodmix",
    "xhibit_vton", "xhibit_remix", "beeple_ai",
]
available_tools = get_comfyui_tools("../workflows/workspaces")
available_tools.update(get_comfyui_tools("../private_workflows/workspaces"))
available_tools.update(get_tools("tools"))
available_tools.update(get_tools("writing_tools"))
if env == "PROD":
    available_tools = {k: v for k, v in available_tools.items() if k in prod_tools}
