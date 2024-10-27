from modal_tool import ModalTool

tool = ModalTool.from_dir('example_tool')






# result = tool.run(args={
#     "name": "world"
# })

# result = tool.run(args={
#     "name": "world"
# })
# print(result)
from bson import ObjectId


result = tool.run_task(
    env="STAGE",
    user=ObjectId("666666666666666666666666"),
    args={
        "name": "world"
    }
)


print(result)
