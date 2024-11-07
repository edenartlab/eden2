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
    try:
        result = await tool.async_run(tool.test_args, env="STAGE")
        eden_utils.pprint(f"Tool: {tool.key}:", result, color="green")
        return result
    except Exception as error:
        eden_utils.pprint(f"Tool: {tool.key}: ERROR {error}", color="red")
        return {"error": f"{error}"}

async def run_all_tests():
    tools = get_tools("tools")
    tools.update(get_tools("../../workflows"))
    # tools.update(get_tools("../../private_workflows"))

    if args.tools:
        tools = {k: v for k, v in tools.items() if k in args.tools}

    print(f"Testing tools: {', '.join(tools.keys())}")

    results = await asyncio.gather(*[run_test(tool) for tool in tools.values()])    
    # results = [[{'mediaAttributes': {'mimeType': 'image/jpeg', 'width': 1024, 'height': 1024, 'aspectRatio': 1.0}, 'url': 'https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/62946527441201f82e0e3d667fda480e176e9940a2e04f4e54c5230665dfc6f6.jpg'}], [{'mediaAttributes': {'mimeType': 'image/jpeg', 'width': 1024, 'height': 1024, 'aspectRatio': 1.0}, 'intermediate_outputs': {'key1': 'value1', 'key2': {'filename': '62946527441201f82e0e3d667fda480e176e9940a2e04f4e54c5230665dfc6f6.jpg', 'mediaAttributes': {'mimeType': 'image/jpeg', 'width': 1024, 'height': 1024, 'aspectRatio': 1.0}}, 'key3': 'args'}, 'url': 'https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/62946527441201f82e0e3d667fda480e176e9940a2e04f4e54c5230665dfc6f6.jpg'}], {'output': ['https://replicate.delivery/yhqm/tWdmL0zKlSqhA5iAIOR4w2Yu9wZlB7X5H0kMUlxezmEIC62JA/out.mp3']}, {'output': ['https://replicate.delivery/yhqm/aorbQeOVEST7FKjFEZgAVedOrhG5vFbu8aN2HMrPxxISE0tTA/out-0.png']}]
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
