import sys
sys.path.append(".")
import os
import json
import asyncio
import argparse
import requests
from datetime import datetime
# from concurrent.futures import ThreadPoolExecutor

parser = argparse.ArgumentParser(description="Test all ComfyUI workflows")
parser.add_argument("--workflows", type=str, help="Which workflows to deploy (comma-separated)", default=None)
parser.add_argument("--production", action='store_true', help="Deploy to production (otherwise staging)")
parser.add_argument("--save", action='store_true', help="Save results to a folder")
args = parser.parse_args()

if args.production:
    os.environ["ENV"] = "PROD"

from tools import get_tools
workflows = get_tools("../workflows")
if args.workflows:
    workflows = {k: workflows[k] for k in args.workflows.split(",")}

async def test_tool(workflow_name):
    try:
        tool = workflows[workflow_name]
        result = await tool.async_run(tool.test_args())
        print(workflow_name, result)
        return {"output":result}
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
        elif "output" in result:
            for i, output in enumerate(result["output"]):
                file_ext = output.split(".")[-1]
                file_path = os.path.join(results_dir, f"{workflow}_{i}.{file_ext}")
                response = requests.get(output)
                with open(file_path, "wb") as f:
                    f.write(response.content)


if __name__ == "__main__":
    asyncio.run(run_all_tests())

