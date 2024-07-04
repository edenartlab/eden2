import json
import asyncio
from tools import get_tools

APP_NAME = "comfyui-dev"

tools = get_tools("../workflows")

workflows = [
    "txt2img", "txt2img2",
    "SD3", "face_styler",
    "txt2vid", "txt2vid_lora",
    "img2vid", "vid2vid", "style_mixing",
    "video_upscaler", 
    "xhibit/vton", "xhibit/remix", 
    "moodmix", "inpaint"
]

# workflows = ["txt2img"]

async def test_tool(tool_name):
    tool = tools[tool_name]
    result = await tool.execute(tool_name, tool.test_args()) 
    print(tool_name, result)
    return result
    
async def run_all_tests():
    tasks = [test_tool(workflow) for workflow in workflows]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    results_dict = {workflow: result for workflow, result in zip(workflows, results)}
    print(json.dumps(results_dict, indent=4))
    
asyncio.run(run_all_tests())