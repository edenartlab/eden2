from datetime import datetime
from pprint import pprint
import asyncio
import argparse
import os
import requests

import eden_utils
from tool import get_tools

parser = argparse.ArgumentParser(description="Test all tools including ComfyUI workflows")
parser.add_argument("--tools", type=str, nargs='+', help="Which tools to test (space-separated)", default=None)
parser.add_argument("--save", action='store_true', help="Save results to a folder")
args = parser.parse_args()

async def run_test(tool):
    result = await tool.async_run(tool.test_args, env="STAGE")
    if "error" in result:
        eden_utils.pprint(f"Tool: {tool.key}: ERROR {result['error']}", color="red")
    else:
        eden_utils.pprint(f"Tool: {tool.key}:", result, color="green")
    return result
        
async def run_all_tests():
    tools = get_tools("tools")
    tools.update(get_tools("../../workflows"))
    # tools.update(get_tools("../../private_workflows"))
    if args.tools:
        tools = {k: v for k, v in tools.items() if k in args.tools}
    print(f"Testing tools: {', '.join(tools.keys())}")
    results = await asyncio.gather(*[run_test(tool) for tool in tools.values()])
    if args.save:
        save_results(tools, results)

    return results

def save_results(tools, results):
    results_dir = f"tests_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    os.makedirs(results_dir, exist_ok=True)
    for tool, result in zip(tools, results):
        pprint(result)
        if "error" in result:
            file_path = os.path.join(results_dir, f"{tool.key}_ERROR.txt")
            with open(file_path, "w") as f:
                f.write(result["error"])
        else:
            result = result if isinstance(result, list) else [result]
            for i, res in enumerate(result):
                if "url" not in res:
                    continue
                ext = res.get("url").split(".")[-1]
                filename = f"{tool}_{i}.{ext}" if len(result) > 1 else f"{tool}.{ext}"
                file_path = os.path.join(results_dir, filename)
                response = requests.get(res.get("url"))
                with open(file_path, "wb") as f:
                     f.write(response.content)

if __name__ == "__main__":
    asyncio.run(run_all_tests())
