from tool import *

style_transfer = Tool.load_from_dir(tool_dir="tools/style_transfer")
txt2img = Tool.load_from_dir(tool_dir="../../workflows/workspaces/img_tools/workflows/txt2img")

print(style_transfer)


save_tool_from_dir(tool_dir="tools/style_transfer", env="STAGE")
save_tool_from_dir(tool_dir="../../workflows/workspaces/img_tools/workflows/txt2img", env="STAGE")

# txt2img.save(env="STAGE")

style_transfer2 = Tool.load(key="style_transfer", env="STAGE")
txt2img2 = Tool.load(key="txt2img", env="STAGE")


print(style_transfer2)
print(txt2img2)


print("-"*100)
print(style_transfer.model_dump())
print(style_transfer2.model_dump())
print("-"*100)

print(txt2img.model_dump())
print(txt2img2.model_dump())







# print(tool_dirs)

# print("-"*100)

# flux2 = tool.Tool.from_dir(tool_dir="tools/flux_schnell")
# print("-"*100)
# print(flux2.model_fields.keys())
# print("-"*100)

# print("\n\n\n\n\n\n\n\n\n")


# tool.save_tool(tool_dir="tools/style_transfer", env="STAGE")


# def __do__():
#     api_file = os.path.join(tool_dir, 'api.yaml')
#     with open(api_file, 'r') as f:
#         schema = yaml.safe_load(f)

#     key = tool_dir.split("/")[-1]
#     schema["key"] = key

#     if schema.get("parent_tool"):        
#         all_tool_dirs = _get_tool_dirs()
#         parent_tool_dir = all_tool_dirs[schema["parent_tool"]]

#         parent_api_file = os.path.join(parent_tool_dir, 'api.yaml')
#         with open(parent_api_file, 'r') as f:
#             parent_schema = yaml.safe_load(f)
        
#         parent_schema["parameter_presets"] = schema.pop("parameters")
#         for k, v in parent_schema["parameter_presets"].items():
#             parent_schema["parameters"][k].update(v)
#         parent_schema.update(schema)
#         schema = parent_schema

#     elif schema.get("handler") == "comfyui":
#         schema["workspace"] = tool_dir.split('/')[-3]

#     test_args_file = os.path.join(tool_dir, 'test.json')
#     with open(test_args_file, 'r') as f:
#         schema["test_args"] = json.load(f)

#     tools = get_collection("tools2", env=env)
#     tools.replace_one({"key": key}, schema, upsert=True)