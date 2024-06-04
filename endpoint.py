import re
import os
import yaml
import json
import httpx
import shutil
import tarfile
import tempfile
import pathlib
import random
from tqdm import tqdm
from enum import Enum
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field, ValidationError, create_model

from utils import download_file


TYPE_MAPPING = {
    'bool': bool,
    'string': str,
    'int': int,
    'float': float,
    'image': str,
    'video': str,
    'audio': str,
    'zip': str,
    'lora': str
}

class ParameterType(str, Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    ZIP = "zip"
    LORA = "lora"
    BOOL_ARRAY = "bool[]"
    INT_ARRAY = "int[]"
    FLOAT_ARRAY = "float[]"
    STRING_ARRAY = "string[]"
    IMAGE_ARRAY = "image[]"
    VIDEO_ARRAY = "video[]"
    AUDIO_ARRAY = "audio[]"
    ZIP_ARRAY = "zip[]"
    LORA_ARRAY = "lora[]"

FILE_TYPES = [ParameterType.IMAGE, ParameterType.VIDEO, ParameterType.AUDIO, ParameterType.ZIP, ParameterType.LORA]
FILE_ARRAY_TYPES = [ParameterType.IMAGE_ARRAY, ParameterType.VIDEO_ARRAY, ParameterType.AUDIO_ARRAY, ParameterType.ZIP_ARRAY, ParameterType.LORA_ARRAY]


class ComfyUIInfo(BaseModel):
    node_id: int
    field: str
    subfield: str
    preprocessing: Optional[str] = None


class EndpointParameter(BaseModel):
    name: str
    label: str
    description: str = Field(None, description="Human-readable description of what parameter does")
    tip: str = Field(None, description="Additional tips for a user or LLM on how to use this parameter properly")
    type: ParameterType
    required: bool = Field(False, description="Indicates if the field is mandatory")
    default: Optional[Any] = Field(None, description="Default value")
    minimum: Optional[float] = Field(None, description="Minimum value for int or float type")
    maximum: Optional[float] = Field(None, description="Maximum value for int or float type")
    min_length: Optional[int] = Field(None, description="Minimum length for array type")
    max_length: Optional[int] = Field(None, description="Maximum length for array type")
    choices: Optional[List[Any]] = Field(None, description="Allowed values")
    comfyui: Optional[ComfyUIInfo] = Field(None)


class Endpoint(BaseModel):
    key: str
    name: str
    description: str = Field(..., description="Human-readable description of what the endpoint does")
    tip: Optional[str] = Field(None, description="Additional tips for a user or LLM on how to get what they want out of this endpoint")
    comfyui_output_node_id: Optional[int] = Field(None, description="ComfyUI node ID of output media")
    parameters: List[EndpointParameter]
    BaseModel: BaseModel = None

    def __init__(self, data, key):
        super().__init__(**data, key=key)
        self.BaseModel = self.create_endpoint_model()

    def create_endpoint_model(self):
        fields = {
            param.name: get_field_type_and_kwargs(param) 
            for param in self.parameters
        }
        EndpointModel = create_model(
            self.key,
            **fields
        )
        EndpointModel.__doc__ = f'{self.description}. {self.tip}.'
        return EndpointModel

    def summary(self, include_params=True):
        summary = f'"{self.key}" :: {self.name} - {self.description}.'
        if self.tip:
            summary += f" {self.tip}."
        if include_params:
            summary += f'\n\n{self.parameters_summary()}'
        return summary

    def parameters_summary(self):
        summary = "Parameters\n---"
        for param in self.parameters:
            summary += f"\n{param.name}: {param.description}."
            if param.tip:
                summary += f" {param.tip}."
            requirements = ["Type: " + param.type.name]
            if not param.default:
                requirements.append("Field required")
            if param.choices:
                requirements.append("Allowed choices: " + ", ".join(param.choices))
            if param.minimum or param.maximum:
                requirements.append(f"Range: {param.minimum} to {param.maximum}")
            if param.min_length or param.max_length:
                requirements.append(f"Allowed length: {param.min_length} to {param.max_length}")
            requirements_str = "; ".join(requirements)
            summary += f" ({requirements_str})"   

        return summary

    # def tool_schema(self):
    #     return {
    #         "type": "function",
    #         "function": openai_schema(self.BaseModel).openai_schema
    #     }
    
    async def execute(self, workflow: str, config: dict):
        import modal
        cls = modal.Cls.lookup("comfyui", workflow)
        result = await cls().api.remote.aio(config)
        if 'error' in result:
            raise Exception("Tool error: " + result['error'])
        print(result)
        return result
        # print(self.tool_schema())


def get_field_type_and_kwargs(param: EndpointParameter) -> (Type, Dict[str, Any]):
    field_kwargs = {
        'description': param.description,
    }

    is_list = param.type.endswith('[]')
    field_type = TYPE_MAPPING[param.type.rstrip('[]')]
    
    if is_list:
        field_type = List[field_type]
        if param.min_length is not None:
            field_kwargs['min_items'] = param.min_length
        if param.max_length is not None:
            field_kwargs['max_items'] = param.max_length

    default = param.default
    if default == 'random':
        assert not param.minimum or not param.maximum, \
            "If default is random, minimum and maximum must be specified"
        field_kwargs['default_factory'] = lambda min_val=param.minimum, max_val=param.maximum: random.randint(min_val, max_val)
    elif default is not None:
        #field_kwargs['default'] = default
        field_kwargs['default_factory'] = lambda: default
    else:
        if param.required:
            field_kwargs['default'] = ...
        else:
            # If not required, set the field type to Optional and default to None
            field_type = Optional[field_type]
            field_kwargs['default'] = None
        
    #elif default:
    #    field_kwargs['default_factory'] = lambda: default
    #elif not default and not param.required: 
        #field_kwargs['default_factory'] = lambda: list() if is_list else None
        #print("ok")

    if param.minimum is not None:
        field_kwargs['ge'] = param.minimum
    if param.maximum is not None:
        field_kwargs['le'] = param.maximum
    if param.choices is not None:
        field_kwargs['choices'] = param.choices

    #if not param.required:
    #field_type = Optional[field_type]

    return (field_type, Field(**field_kwargs))
            

def load_tool(tool_name: str, tool_path: str) -> Endpoint:
    if not os.path.exists(tool_path):
        raise ValueError(f"Tool API not found: {tool_path}")
    data = yaml.safe_load(open(tool_path, "r"))
    tool = Endpoint(data, key=tool_name)    
    return tool


def get_tools(tools_folder: str):
    tool_names = [
        name for name in os.listdir(tools_folder)
        if os.path.isdir(os.path.join(tools_folder, name)) and not name.startswith('.')
    ]
    if not tool_names:
        raise ValueError(f"No tools found in {tools_folder}")
    tools = {
        name: load_tool(name, os.path.join(tools_folder, name, "api.yaml"))
        for name in tool_names
    }
    return tools


def get_tools_summary(tools: List[Endpoint]):    
    tools_summary = ""
    for tool in tools.values():
        tools_summary += f"{tool.summary(include_params=False)}\n"
    return tools_summary


def prepare_args(tool, user_args, save_files=False):
    args = {}
    print(user_args)

    for param in tool.parameters:
        key = param.name
        value = None

        if param.default is not None:
            value = param.default
        if user_args.get(key) is not None:
            value = user_args[key]

        if value == "random":
            value = random.randint(param.minimum, param.maximum)

        # if param.required and value is None:
        #     raise ValueError(f"Required argument '{key}' is missing")

        if param.type == ParameterType.LORA:
            if value is None:
                value = None
            else:
                lora_tarfile = download_file(value, "/root/downloads/")
                lora_name, embedding_name = untar_and_move(
                    lora_tarfile, 
                    downloads_folder="/root/downloads",
                    loras_folder="/root/models/loras",
                    embeddings_folder="/root/models/embeddings"
                )
                value = lora_name

        elif param.type in [ParameterType.IMAGE, ParameterType.VIDEO, ParameterType.AUDIO]:
            value = download_file(value, "/root/input") if value else None

        elif param.type in [ParameterType.IMAGE_ARRAY, ParameterType.VIDEO_ARRAY, ParameterType.AUDIO_ARRAY]:
            value = [download_file(v, "/root/input") if v else None for v in value]

        args[key] = value

    try:
        tool.BaseModel(**args)
    except ValidationError as err:
        raise ValueError(f"Invalid arguments: {err.errors()}")
    
    return args


def inject_args_into_workflow(workflow, tool, args):
    comfyui_map = {
        param.name: param.comfyui 
        for param in tool.parameters if param.comfyui
    }
    
    for key, comfyui in comfyui_map.items():
        value = args.get(key)
        if value is None:
            continue

        if comfyui.preprocessing is not None:
            if comfyui.preprocessing == "csv":
                value = ",".join(value)

            elif comfyui.preprocessing == "folder":
                temp_subfolder = tempfile.mkdtemp(dir="/root/input")
                if isinstance(value, list):
                    for i, file in enumerate(value):
                        filename = f"{i:06d}_{os.path.basename(file)}"
                        new_path = os.path.join(temp_subfolder, filename)
                        shutil.move(file, new_path)
                else:
                    shutil.move(value, temp_subfolder)
                value = temp_subfolder

        node_id, field, subfield = str(comfyui.node_id), comfyui.field, comfyui.subfield
        workflow[node_id][field][subfield] = value

    return workflow



# def download_file(url, destination_folder):
#     destination_folder = pathlib.Path(destination_folder)
#     destination_folder.mkdir(exist_ok=True)
#     local_filepath = destination_folder / url.split("/")[-1]
    
#     print(f"downloading {url} ... to {local_filepath}")

#     with httpx.stream("GET", url, follow_redirects=True) as stream:
#         total = int(stream.headers["Content-Length"])
#         with open(local_filepath, "wb") as f, tqdm(
#             total=total, unit_scale=True, unit_divisor=1024, unit="B"
#         ) as progress:
#             num_bytes_downloaded = stream.num_bytes_downloaded
#             for data in stream.iter_bytes():
#                 f.write(data)
#                 progress.update(
#                     stream.num_bytes_downloaded - num_bytes_downloaded
#                 )
#                 num_bytes_downloaded = stream.num_bytes_downloaded

#     return str(local_filepath)


def untar_and_move(
    source_tar: str,
    downloads_folder: str,
    loras_folder: str,
    embeddings_folder: str,
):
    if not os.path.exists(source_tar):
        raise FileNotFoundError(f"The source tar file {source_tar} does not exist.")

    name = os.path.basename(source_tar).split(".")[0]
    destination_folder = os.path.join(downloads_folder, name)
    if os.path.exists(destination_folder):
        print("Destination folder already exists. Skipping.")
    else:
        try:
            with tarfile.open(source_tar, "r:*") as tar:
                tar.extractall(path=destination_folder)
                print("Extraction complete.")
        except Exception as e:
            raise IOError(f"Failed to extract tar file: {e}")

    extracted_files = os.listdir(destination_folder)
    pattern = re.compile(r"^(.+)_embeddings\.safetensors$")
    
    # Find the base name X for the files X.safetensors and X_embeddings.safetensors
    base_name = None
    for file in extracted_files:
        match = pattern.match(file)
        if match:
            base_name = match.group(1)
            break
    
    if base_name is None:
        raise FileNotFoundError("No matching files found for pattern X_embeddings.safetensors.")
    
    lora_filename = f"{base_name}.safetensors"
    embeddings_filename = f"{base_name}_embeddings.safetensors"

    for file in [lora_filename, embeddings_filename]:
        if str(file) not in extracted_files:
            raise FileNotFoundError(f"Required file {file} does not exist in the extracted files.")

    if not os.path.exists(loras_folder):
        os.makedirs(loras_folder)
    if not os.path.exists(embeddings_folder):
        os.makedirs(embeddings_folder)

    lora_path = os.path.join(destination_folder, lora_filename)
    embeddings_path = os.path.join(destination_folder, embeddings_filename)

    # Copy the lora file to the loras folder
    lora_copy_path = os.path.join(loras_folder, lora_filename)
    shutil.copy(lora_path, lora_copy_path)
    print(f"LoRA {lora_path} has been moved to {lora_copy_path}.")

    # Copy the embedding file to the embeddings folder
    embeddings_filename = embeddings_filename.replace("_embeddings.safetensors", ".safetensors") 
    embeddings_copy_path = os.path.join(embeddings_folder, embeddings_filename)
    shutil.copy(embeddings_path, embeddings_copy_path)
    print(f"Embeddings {embeddings_path} has been moved to {embeddings_copy_path}.")

    return lora_filename, embeddings_filename


