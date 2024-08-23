import sys
sys.path.append(".")
import os
import json
import asyncio
import argparse
import pathlib
import requests
from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor

from tool import get_tools

parser = argparse.ArgumentParser(description="Test all ComfyUI workflows")
parser.add_argument("--envs", type=str, help="Which environments to test (comma-separated)", default=None)
parser.add_argument("--production", action='store_true', help="Test production (otherwise staging)")
parser.add_argument("--save", action='store_true', help="Save results to a folder")
args = parser.parse_args()

if args.production:
    os.environ["ENV"] = "PROD"


envs_dir = pathlib.Path("../workflows/environments")
envs = [f.name for f in envs_dir.iterdir() if f.is_dir()]

if args.envs:
    envs_ = args.envs.split(",")
    if not all(env in envs for env in envs_):
        raise ValueError(f"One or more of the requested environments not found in {envs_dir}") 
    envs = envs_

workflows = {
    k: v for env in envs 
    for k, v in get_tools(f"{envs_dir}/{env}/workflows").items()
}

print("Running tests:", ", ".join(workflows.keys()))

async def test_tool(workflow_name):
    try:
        tool = workflows[workflow_name]
        output = await tool.async_run(tool.test_args)
        result = tool.get_user_result(output)
        print(workflow_name, result)
        return {"result": result}
    except Exception as e:
        return {"error": f"{e}"}

async def run_all_tests():
    print(f"Running tests: {', '.join(workflows.keys())}")
    tasks = [test_tool(workflow) for workflow in workflows]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    results_dict = {workflow: result for workflow, result in zip(workflows, results)}
    print(json.dumps(results_dict, indent=4))
    if args.save:
       save_results(results_dict) 

def save_results(results_dict):
    results_dir = f"tests_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    os.makedirs(results_dir, exist_ok=True)
    for workflow, result in results_dict.items():
        if "error" in result:
            file_path = os.path.join(results_dir, f"{workflow}_ERROR.txt")
            with open(file_path, "w") as f:
                f.write(result["error"])
        elif "result" in result:
            for i, output in enumerate(result["result"]):
                file_ext = output.split(".")[-1]
                file_path = os.path.join(results_dir, f"{workflow}_{i}.{file_ext}")
                response = requests.get(output)
                with open(file_path, "wb") as f:
                    f.write(response.content)


if __name__ == "__main__":
    asyncio.run(run_all_tests())

