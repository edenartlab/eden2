from tool import *

# Usage:
#tool = Tool.from_dir('person')
tool = ComfyUITool.from_dir('example_tool')

# print(regular_tool)
print(tool)
print(tool.comfyui_map)

print(tool.base_model.__fields__['age'])


args = tool.prepare_args({
    'type': 'thingy',
    'name': 'John', 
    'age': 30, 
    'price': 1,
    'skills': ["cooking", "swimming"],
    'contacts': [
        {'type': 'emai3l', 'value': 'widget@hotmail.com'},
        {'type': 'phon3e', 'value': '555-1234'},
    ]
})

print("-======")
print(args)


