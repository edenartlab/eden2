import tool

tool_dirs = tool._get_tool_dirs()
# print(tool_dirs)

# print("-"*100)

# flux2 = tool.Tool.from_dir(tool_dir="tools/flux_schnell")
# print("-"*100)
# print(flux2.model_fields.keys())
# print("-"*100)

# print("\n\n\n\n\n\n\n\n\n")
style_transfer = tool.Tool.from_dir(tool_dir="tools/style_transfer")

# tool.save_tool(tool_dir="tools/style_transfer", env="STAGE")

from pprint import pprint
# pprint(style_transfer)
# print("="*100)
# print(style_transfer.model_fields.keys())
# print("="*100)




style_transfer2 = tool.Tool.from_mongo(key="style_transfer", env="STAGE")
print("-"*100)
print(style_transfer2.model_fields.keys())
print("-"*100)

