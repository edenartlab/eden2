import sys
sys.path.append(".")
import os
import json
import asyncio
import argparse
import pathlib
import requests
from datetime import datetime

from tool import get_tools
import eden_utils
from models import User, Task
from tool import load_tool, get_tools

# parser = argparse.ArgumentParser(description="Test all tools including ComfyUI workflows")
# parser.add_argument("--tools", type=str, nargs='+', help="Which tools to test (space-separated)", default=None)
# parser.add_argument("--workspaces", type=str, nargs='+', help="Which workspaces to test (space-separated)", default=None)
# parser.add_argument("--save", action='store_true', help="Save results to a folder")
# args = parser.parse_args()

# if args.workspaces and args.tools:
#     raise ValueError("Cannot specify both --workspaces and --tools")

# tools = {}
# if args.tools:
#     for workspaces_dir in [pathlib.Path("../workflows/workspaces"), pathlib.Path("../private_workflows/workspaces")]:
#         workspaces = [f.name for f in workspaces_dir.iterdir() if f.is_dir()]
#         tools.update({
#             k: v for env in workspaces 
#             for k, v in get_tools(f"{workspaces_dir}/{env}/workflows").items()
#         })
#     tools.update(get_tools("tools"))
#     if not all(tool in tools for tool in args.tools):
#         raise ValueError(f"One or more of the requested tools not found") 
#     tools = {k: v for k, v in tools.items() if k in args.tools}
# elif args.workspaces:
#     for workspaces_dir in [pathlib.Path("../workflows/workspaces"), pathlib.Path("../private_workflows/workspaces")]:
#         tools.update({
#             k: v for workspace in args.workspaces 
#             for k, v in get_tools(f"{workspaces_dir}/{workspace}/workflows").items()
#         })
# else:
#     workspaces_dirs = [pathlib.Path("../workflows/workspaces"), pathlib.Path("../private_workflows/workspaces")]
#     for workspaces_dir in workspaces_dirs:
#         workspaces = [f.name for f in workspaces_dir.iterdir() if f.is_dir()]
#         for workspace in workspaces:
#             workspace_tools = get_tools(f"{workspaces_dir}/{workspace}/workflows")
#             tools.update(workspace_tools)
#     tools.update(get_tools("tools"))
    
# async def test_tool(workflow_name):
#     # try:
#     if 1:
#         tool = tools[workflow_name]
#         print("test", tool)
#         print("test", tool.test_args)
#         output = await tool.async_run(tool.test_args)
#         result = tool.get_user_result(output)
#         print(json.dumps({workflow_name: result}, indent=4))
#         return {"result": result}
#     # except Exception as e:
#         # return {"error": f"{e}"}

# async def run_all_tests():
#     tasks = [
#         create_and_run_task(tool, tool.test_args, env, user_id)
#         for key, tool in tools.items()
#     ]
#     results = await asyncio.gather(*tasks, return_exceptions=True)
#     return results

# # Replace the sequential loop with the parallel execution
# asyncio.run(run_all_tests())

# def save_results(results_dict):
#     results_dir = f"tests_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
#     os.makedirs(results_dir, exist_ok=True)
#     for tool, result in results_dict.items():
#         if "error" in result:
#             file_path = os.path.join(results_dir, f"{tool}_ERROR.txt")
#             with open(file_path, "w") as f:
#                 f.write(result["error"])
#         elif "result" in result:
#             for i, output in enumerate(result["result"]):
#                 file_ext = output.split(".")[-1]
#                 file_path = os.path.join(results_dir, f"{tool}_{i}.{file_ext}")
#                 response = requests.get(output)
#                 with open(file_path, "wb") as f:
#                     f.write(response.content)

# if __name__ == "__main__":
#     asyncio.run(run_all_tests())

env = "STAGE"
user_id = os.getenv("EDEN_TEST_USER_STAGE")


tools = get_tools("tools")



async def create_and_run_task(tool, args, env, user_id):
    user = User.load(user_id, env)
    args = tool.prepare_args(args)
    cost = tool.calculate_cost(args.copy())
    user.verify_manna_balance(cost)
    task = Task(
        env=env,
        workflow=tool.key,
        output_type="image", 
        args=args,
        user=user_id,
        cost=cost,
        status="pending"
    )
    task.save()
    handler_id = await tool.async_start_task(task)
    task.update(handler_id=handler_id)
    user.spend_manna(task.cost)
    result = await tool.async_wait(task)
    eden_utils.pprint(f"Tool: {tool.key}:", result)
    return result


async def run_all_tests():
    tasks = {
        key: await create_and_run_task(tool, tool.test_args, env, user_id)
        for key, tool in tools.items()
    }
    results = {
        key: await task
        for key, task in tasks.items()
    }

    # for key, result in results.items():
    #     eden_utils.pprint(f"\n\nTool: {key}:", result)
    
    return results

# Replace the sequential loop with the parallel execution
asyncio.run(run_all_tests())
