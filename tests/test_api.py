import sys
sys.path.append(".")
import os
import json
import concurrent.futures
# import asyncio
import argparse
import pathlib
import dotenv
import requests
from datetime import datetime

from tool import get_tools

parser = argparse.ArgumentParser(description="Test all tools including ComfyUI workflows")
parser.add_argument("--tools", type=str, nargs='+', help="Which tools to test (space-separated)", default=None)
parser.add_argument("--production", action='store_true', help="Test production (otherwise staging)")
parser.add_argument("--save", action='store_true', help="Save results to a folder")
args = parser.parse_args()

save = args.save
os.environ["ENV"] = "PROD" if args.production else "STAGE"

dotenv.load_dotenv()
EDEN_ADMIN_KEY = os.getenv("EDEN_ADMIN_KEY")
EDEN_TEST_USER = os.getenv("EDEN_TEST_USER")
MODAL_DEV_API_URL = os.getenv("MODAL_DEV_API_URL") 
print("MODAL_DEV_API_URL", MODAL_DEV_API_URL)

envs_dir = pathlib.Path("../workflows/workspaces")
envs = [f.name for f in envs_dir.iterdir() if f.is_dir()]
tools = {
    k: v for env in envs 
    for k, v in get_tools(f"{envs_dir}/{env}/workflows").items()
}
envs_dir = pathlib.Path("../private_workflows/workspaces")
envs = [f.name for f in envs_dir.iterdir() if f.is_dir()]
tools.update({
    k: v for env in envs 
    for k, v in get_tools(f"{envs_dir}/{env}/workflows").items()
})
tools.update(get_tools("tools"))

if args.tools:
    if not all(tool in tools for tool in args.tools):
        raise ValueError(f"One or more of the requested tools not found") 
    tools = {k: v for k, v in tools.items() if k in args.tools}

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

def test_api_tool(tool_name, args):
    try:
        headers = {
            "Authorization": f"Bearer {EDEN_ADMIN_KEY}", 
            "Content-Type": "application/json"
        }
        task = {
            "workflow": tool_name,
            "args": args,
            "user": EDEN_TEST_USER
        }
        # task = {
        #     "workflow": tool_name,
        #     "args": {"prompt": "a blue cat", "width": 50000},
        #     "user": EDEN_TEST_USER
        # }
        # print(task)
        response = requests.post(MODAL_DEV_API_URL, json=task, headers=headers)
        # print(response)
        # print(response.status_code)
        # print(response.json())
        return {
            "status_code": response.status_code,
            "content": response.json() if response.headers.get('content-type') == 'application/json' else response.text,
            "headers": dict(response.headers)
        }
    except Exception as e:
        return {"error": f"{e}"}


def run_all_tests():
    print(f"Running tests: {', '.join(tools.keys())}")
    results_dict = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_tool = {executor.submit(test_api_tool, tool, tools[tool].test_args): tool for tool in tools}
        for future in concurrent.futures.as_completed(future_to_tool):
            tool = future_to_tool[future]
            try:
                result = future.result()
                results_dict[tool] = result
            except Exception as exc:
                results_dict[tool] = {"error": f"{exc}"}
    
    print(json.dumps(results_dict, indent=4))
    if save:
        save_results(results_dict)

if __name__ == "__main__":
    run_all_tests()

