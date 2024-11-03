from comfyui_tool import ComfyUITool

tool = ComfyUITool.from_dir('../../workflows/workspaces/img_tools/workflows/txt2img')
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

async def submit(tool_dir, args, env, user_id):
    tool = ComfyUITool.from_dir(tool_dir)
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
    handler_id = await tool.async_run_task(task)
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
        tool_dir='../../workflows/workspaces/img_tools/workflows/txt2img',
        args = {
            "prompt": "a dog in the style of Starry Night",
            # "style_image": "https://edenartlab-stage-data.s3.us-east-1.amazonaws.com/62946527441201f82e0e3d667fda480e176e9940a2e04f4e54c5230665dfc6f6.jpg"
            # TODO: style_image none is not working
        }, 
        env="STAGE", 
        user_id="65284b18f8bbb9bff13ebe65"
    )
    return result

import asyncio
result = asyncio.run(main())


print(result)






# for name, param in tool.comfyui_map.items():
#     node_id, field, subfield, remap = param.get('node_id'), param.get('field'), param.get('subfield'), param.get('remap')
#     subfields = [s.strip() for s in subfield.split(",")]
#     print(name, ":", node_id, field, subfields, remap)
    
# print('-----')


# for name, param in tool.base_model.__fields__.items():
#     metadata = param.json_schema_extra or {}
#     file_type = metadata.get('file_type')
#     is_array = metadata.get('is_array')
    
#     if file_type in ["image", "video", "audio", "lora", "zip"]:
#         print("FILE", name, file_type, is_array)


        