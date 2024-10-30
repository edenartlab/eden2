from comfyui_tool import ComfyUITool

tool = ComfyUITool.from_dir('tools/txt2img')
print(tool)



# raise Exception("Not implemented")




# result = tool.run(args={
#     "name": "world"
# })

# result = tool.run(args={
#     "name": "world"
# })
# print(result)



# result = tool.run(
#     # env="STAGE",
#     # user=ObjectId("666666666666666666666666"),
#     args={
#         "name": "w22orld"
#     }
# )
from models import User, Task
from bson import ObjectId
async def submit(tool_name, args, env, user_id):
    tool = ModalTool.from_dir(tool_name)
    user = User.load(user_id, env)
    args = tool.prepare_args(args)
    print(args)
    cost = tool.calculate_cost(args.copy())
    user.verify_manna_balance(cost)
    task = Task(
        env=env,
        workflow=tool.key,
        output_type="image", 
        args=args,
        user=ObjectId(user_id),
        cost=cost,
        status="pending"
    )
    task.save()
    handler_id = await tool.async_submit(task)
    task.update(handler_id=handler_id)
    user.spend_manna(task.cost)            
    return handler_id



# result = tool.submit(
#     args={
#         "name": "w332orld"
#     },
#     env="STAGE",
#     user=ObjectId("65284b18f8bbb9bff13ebe65"),
# )


async def main():
    result = await submit(
        tool_name='tools/txt2img', 
        args = {
            "prompt": "a dog in the style of Starry Night"
        }, 
        env="STAGE", 
        user_id="65284b18f8bbb9bff13ebe65"
    )
    return result

# import asyncio
# result = asyncio.run(main())


# print(result)




