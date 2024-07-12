import sys
sys.path.append(".")
import os
import json
import asyncio
import argparse
# from concurrent.futures import ThreadPoolExecutor

parser = argparse.ArgumentParser(description="Test all ComfyUI workflows")
parser.add_argument("--workflows", type=str, help="Which workflows to deploy (comma-separated)", default=None)
parser.add_argument("--production", action='store_true', help="Deploy to production (otherwise staging)")
args = parser.parse_args()

if args.production:
    os.environ["ENV"] = "PROD"

from tools import get_tools
workflows = get_tools("../workflows", exclude=["blend"])
if args.workflows:
    workflows = {k: workflows[k] for k in args.workflows.split(",")}

async def test_tool(workflow_name):
    try:
        tool = workflows[workflow_name]
        result = await tool.async_run(workflow_name, tool.test_args())
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

