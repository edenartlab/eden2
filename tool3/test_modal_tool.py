from modal_tool import ModalTool

tool = ModalTool.from_dir('tools/tool1')


# result = tool.run(args={
#     "prompt_image": "https://dtut5r9j4w7j4.cloudfront.net/0d42768095507a7bbe2b16c789bf3ceb897de5f0e26297c0e7a68c51623796f9.png",
#     "prompt_text": "Slow zoom in, a floating ceramic head starts singing in the forest"
# })

# print(result)


# result = tool.run(args={
#     "name": "world"
# })
# print(result)
from bson import ObjectId


# result = tool.run(
#     # env="STAGE",
#     # user=ObjectId("666666666666666666666666"),
#     args={
#         "name": "w22orld"
#     }
# )
from models import User, Task

async def submit(tool_dir, args, env, user_id):
    tool = ModalTool.from_dir(tool_dir)
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
    handler_id = await tool.async_start_task(task)
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
        tool_dir="tools/tool2", 
        args = {
            # "name": "hello world",
        
            "prompt_image": "prompt_image",
            "prompt_text": "prompt_text"

            # "prompt_image": "https://dtut5r9j4w7j4.cloudfront.net/0d42768095507a7bbe2b16c789bf3ceb897de5f0e26297c0e7a68c51623796f9.png",
            # "prompt_text": "Slow zoom in, a floating ceramic head starts singing in the forest"
        },         
        env="STAGE", 
        user_id="65284b18f8bbb9bff13ebe65"
    )
    return result


import asyncio
result = asyncio.run(main())
print(result)
