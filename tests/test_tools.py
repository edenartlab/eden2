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

parser = argparse.ArgumentParser(description="Test all tools including ComfyUI workflows")
parser.add_argument("--tools", type=str, nargs='+', help="Which tools to test (space-separated)", default=None)
parser.add_argument("--workspaces", type=str, nargs='+', help="Which workspaces to test (space-separated)", default=None)
parser.add_argument("--save", action='store_true', help="Save results to a folder")
args = parser.parse_args()

if args.workspaces and args.tools:
    raise ValueError("Cannot specify both --workspaces and --tools")

tools = {}
if args.tools:
    for workspaces_dir in [pathlib.Path("../workflows/workspaces"), pathlib.Path("../private_workflows/workspaces")]:
        workspaces = [f.name for f in workspaces_dir.iterdir() if f.is_dir()]
        tools.update({
            k: v for env in workspaces 
            for k, v in get_tools(f"{workspaces_dir}/{env}/workflows").items()
        })
    tools.update(get_tools("tools"))
    unrecognized_tools = [tool for tool in args.tools if tool not in tools]
    if unrecognized_tools:
        raise ValueError(f"One or more of the requested tools not found: {', '.join(unrecognized_tools)}") 
    tools = {k: v for k, v in tools.items() if k in args.tools}
elif args.workspaces:
    for workspaces_dir in [pathlib.Path("../workflows/workspaces"), pathlib.Path("../private_workflows/workspaces")]:
        tools.update({
            k: v for workspace in args.workspaces 
            for k, v in get_tools(f"{workspaces_dir}/{workspace}/workflows").items()
        })
else:
    workspaces_dirs = [pathlib.Path("../workflows/workspaces"), pathlib.Path("../private_workflows/workspaces")]
    for workspaces_dir in workspaces_dirs:
        workspaces = [f.name for f in workspaces_dir.iterdir() if f.is_dir()]
        for workspace in workspaces:
            workspace_tools = get_tools(f"{workspaces_dir}/{workspace}/workflows")
            tools.update(workspace_tools)
    tools.update(get_tools("tools"))
    
async def test_tool(workflow_name):
    try:
        tool = tools[workflow_name]
        output = await tool.async_run(tool.test_args)
        result = tool.get_user_result(output)
        print(json.dumps({workflow_name: result}, indent=4))
        return {"result": result}
    except Exception as e:
        print("OOPS", e)
        return {"error": f"Error running {workflow_name}: {e}"}

async def run_all_tests():
    print(f"Running tests: {', '.join(tools.keys())}")
    tasks = [test_tool(tool) for tool in tools]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    results_dict = {tool: result for tool, result in zip(tools, results)}
    print("\n\n\n\n=== Final Results ===")
    print(json.dumps(results_dict, indent=4))
    if args.save:
       save_results(results_dict) 

def save_results(results_dict):
    results_dir = f"tests_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    os.makedirs(results_dir, exist_ok=True)
    for tool, result in results_dict.items():
        if "error" in result:
            file_path = os.path.join(results_dir, f"{tool}_ERROR.txt")
            with open(file_path, "w") as f:
                f.write(result["error"])
        elif "result" in result:
            for i, output in enumerate(result["result"]):
                file_ext = output.split(".")[-1]
                file_path = os.path.join(results_dir, f"{tool}_{i}.{file_ext}")
                response = requests.get(output)
                with open(file_path, "wb") as f:
                    f.write(response.content)

if __name__ == "__main__":
    asyncio.run(run_all_tests())
