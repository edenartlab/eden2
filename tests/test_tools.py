import asyncio
import os

from eve.tool import get_tools_from_mongo, get_tools_from_dirs


def test_tools():

    def test_helper(
        tools: list[str],
        yaml: bool, 
        db: str, 
        api: bool, 
        parallel: bool, 
        mock: bool
    ):
        """Test multiple tools with their test args"""

        async def async_test_tool(tool, api, db):
            if api:
                user_id = os.getenv("EDEN_TEST_USER_STAGE")
                task = await tool.async_start_task(user_id, tool.test_args, db=db, mock=mock)
                result = await tool.async_wait(task)
            else:
                result = await tool.async_run(tool.test_args, db=db, mock=mock)        
            return result

        async def async_run_tests(tools, api, db, parallel):
            tasks = [async_test_tool(tool, api, db) for tool in tools.values()]
            if parallel:
                results = await asyncio.gather(*tasks)
            else:
                results = [await task for task in tasks]
            return results

        if yaml:
            all_tools = get_tools_from_dirs()
        else:
            all_tools = get_tools_from_mongo(db=db)

        if tools:
            tools = {k: v for k, v in all_tools.items() if k in tools}
        else:
            tools = all_tools

        results = asyncio.run(
            async_run_tests(tools, api, db, parallel)
        )
        errors = [f"{tool}: {result['error']}" for tool, result in zip(tools.keys(), results) if "error" in result]
        error_list = "\n\t".join(errors)
        print(f"\n\nTested {len(tools)} tools with {len(errors)} errors:\n{error_list}")


    test_helper(
        tools=["flux_schnell", "txt2img", "img2vid", "musicgen"],
        yaml=False,
        db="STAGE",
        api=False,
        parallel=True,
        mock=True
    )
