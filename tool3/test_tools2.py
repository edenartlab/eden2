from datetime import datetime
import asyncio
import json
import os
import requests

from tool import get_tools_from_mongo, get_tools_from_dirs


def save_test_results(tools, results):
    results_dir = f"tests_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    os.makedirs(results_dir, exist_ok=True)
    for tool, result in zip(tools, results):
        print(json.dumps(result, indent=2))
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


async def async_test_tool(tool, api, env):
    if api:
        user_id = os.getenv("EDEN_TEST_USER_STAGE")
        task = await tool.async_start_task(user_id, tool.test_args, env=env)
        result = await tool.async_wait(task)
    else:
        result = await tool.async_run(tool.test_args, env=env)
    
    if "error" in result:
        raise Exception(f"Error for {tool.key}: {result['error']}")
    
    return result


async def async_run_tests(from_dirs, api, env, parallel, save):
    if from_dirs:
        tools = get_tools_from_dirs()
    else:
        tools = get_tools_from_mongo(env=env)

    tasks = [async_test_tool(tool, api, env) for tool in tools.values()]
    if parallel:
        results = await asyncio.gather(*tasks)
    else:
        results = [await task for task in tasks]

    if save:
        save_test_results(tools, results)

    return results


if __name__ == "__main__":
    asyncio.run(
        async_run_tests(
            from_dirs=True, 
            api=True, 
            env="STAGE", 
            parallel=True,
            save=True
        )
    )
