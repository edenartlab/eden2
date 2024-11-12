from datetime import datetime
import asyncio
import os

from eve.tool import get_tools_from_mongo, get_tools_from_dirs
from eve.eden_utils import save_test_results


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

    if save and results:
        save_test_results(tools, results)

    return results


# if __name__ == "__main__":
#     asyncio.run(
#         async_run_tests(
#             from_dirs=True, 
#             api=True, 
#             env="STAGE", 
#             parallel=True,
#             save=True
#         )
#     )


def test_tools():
    asyncio.run(
        async_run_tests(
            from_dirs=True, 
            api=True, 
            env="STAGE", 
            parallel=True,
            save=True
        )
    )
