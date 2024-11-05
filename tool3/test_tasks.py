from models import User, Task
from test_tools import *


async def run_test(tool):
    try:
        user_id = os.getenv("EDEN_TEST_USER_STAGE")
        user = User.load(user_id, "STAGE")
        args = tool.prepare_args(tool.test_args)
        cost = tool.calculate_cost(args.copy())
        user.verify_manna_balance(cost)
        task = Task(
            env="STAGE",
            workflow=tool.key,
            output_type="image", 
            args=args,
            user=user_id,
            cost=cost,
            status="pending"
        )
        task.save()
        handler_id = await tool.async_start_task(task)
        task.update(handler_id=handler_id)
        user.spend_manna(task.cost)
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
    # results = [[{'mediaAttributes': {'mimeType': 'image/jpeg', 'width': 1024, 'height': 1024, 'aspectRatio': 1.0}, 'url': 'https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/62946527441201f82e0e3d667fda480e176e9940a2e04f4e54c5230665dfc6f6.jpg'}], [{'mediaAttributes': {'mimeType': 'image/jpeg', 'width': 1024, 'height': 1024, 'aspectRatio': 1.0}, 'intermediate_outputs': {'key1': 'value1', 'key2': {'filename': '62946527441201f82e0e3d667fda480e176e9940a2e04f4e54c5230665dfc6f6.jpg', 'mediaAttributes': {'mimeType': 'image/jpeg', 'width': 1024, 'height': 1024, 'aspectRatio': 1.0}}, 'key3': 'args'}, 'url': 'https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/62946527441201f82e0e3d667fda480e176e9940a2e04f4e54c5230665dfc6f6.jpg'}], {'output': ['https://replicate.delivery/yhqm/tWdmL0zKlSqhA5iAIOR4w2Yu9wZlB7X5H0kMUlxezmEIC62JA/out.mp3']}, {'output': ['https://replicate.delivery/yhqm/aorbQeOVEST7FKjFEZgAVedOrhG5vFbu8aN2HMrPxxISE0tTA/out-0.png']}]
    if args.save:
        save_results(tools, results)

    return results



if __name__ == "__main__":
    asyncio.run(run_all_tests())
