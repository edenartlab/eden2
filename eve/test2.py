import os

from eve.tool import Tool
from pprint import pprint
tool = Tool.load("flux_schnell", "STAGE")
print(tool)


async def async_main():
    result = await tool.async_run(tool.test_args, env="STAGE")
    print(result)

async def async_main_task():
    user_id = os.getenv("EDEN_TEST_USER_STAGE")
    task = await tool.async_start_task(user_id, tool.test_args, env="STAGE")
    result = await tool.async_wait(task)
    print(result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(async_main())
    asyncio.run(async_main_task())
