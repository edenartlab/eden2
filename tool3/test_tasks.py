from test_tools import *

async def run_test(tool):
    try:
        user_id = os.getenv("EDEN_TEST_USER_STAGE")
        task = await tool.async_start_task(user_id, tool.test_args, "STAGE")
        result = await tool.async_wait(task)
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
    
    if args.save:
        save_results(tools, results)

    return results

if __name__ == "__main__":
    asyncio.run(run_all_tests())
