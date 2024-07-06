import sys
sys.path.append(".")
import json
import asyncio
# from concurrent.futures import ThreadPoolExecutor
from tools import get_tools

APP_NAME = "comfyui-dev"

workflows = get_tools("../workflows", exclude=["blend"])

# workflows = [
#     "txt2img", "txt2img2",
#     "SD3", "face_styler",
#     "txt2vid", "txt2vid_lora",
#     "img2vid", "vid2vid", "style_mixing",
#     "video_upscaler", 
#     "xhibit/vton", "xhibit/remix", 
#     "moodmix", "inpaint"
# ]

# workflows = ["txt2img"]

async def test_tool(workflow_name):
    try:
        tool = workflows[workflow_name]
        result = await tool.run(workflow_name, tool.test_args()) 
        print(workflow_name, result)
        return result
    except Exception as e:
        return f"error {e}"
    
async def run_all_tests():
    tasks = [test_tool(workflow) for workflow in workflows]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    results_dict = {workflow: result for workflow, result in zip(workflows, results)}
    print(json.dumps(results_dict, indent=4))
    
if __name__ == "__main__":
    asyncio.run(run_all_tests())

# def run_all_tests():
#     with ThreadPoolExecutor() as executor:
#         futures = {executor.submit(test_tool, workflow): workflow for workflow in workflows}
#         results_dict = {futures[future]: future.result() for future in futures}
#     print(json.dumps(results_dict, indent=4))

# if __name__ == "__main__":
#     run_all_tests()