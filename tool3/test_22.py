import json
from tool import load_tool

tool = load_tool("../../workflows/workspaces/video/workflows/texture_flow")

workflow = json.loads(open("../../workflows/workspaces/video/workflows/texture_flow/workflow_api.json").read())


print(workflow)

print(tool.comfyui_map)
from enum import Enum


for key, comfy_param in tool.comfyui_map.items():
    node_id, field, subfield, remaps = str(comfy_param.get('node_id')), str(comfy_param.get('field')), str(comfy_param.get('subfield')), comfy_param.get('remap')
    subfields = [s.strip() for s in subfield.split(",")]
    # print(node_id, field, subfields, remap)
    for subfield in subfields:
        if node_id not in workflow or field not in workflow[node_id] or subfield not in workflow[node_id][field]:
            raise Exception(f"Node ID {node_id}, field {field}, subfield {subfield} not found in workflow")
    for remap in remaps or []:
        subfields = [s.strip() for s in str(remap.get('subfield')).split(",")]
        for subfield in subfields:
            if str(remap.get('node_id')) not in workflow or str(remap.get('field')) not in workflow[str(remap.get('node_id'))] or subfield not in workflow[str(remap.get('node_id'))][str(remap.get('field'))]:
                raise Exception(f"Node ID {remap.get('node_id')}, field {remap.get('field')}, subfield {subfield} not found in workflow")
        param = tool.base_model.model_fields[key]
        has_choices = isinstance(param.annotation, type) and issubclass(param.annotation, Enum)
        if not has_choices:
            raise Exception(f"Remap parameter {key} has no original choices")
        choices = [e.value for e in param.annotation]
        if not all(choice in choices for choice in remap['map'].keys()):
            raise Exception(f"Remap parameter {key} has invalid choices: {remap['map']}")
        if not all(choice in remap['map'].keys() for choice in choices):
            raise Exception(f"Remap parameter {key} is missing original choices: {choices}")
        