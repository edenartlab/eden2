import os
import re
import git
import json
import uuid
import time
import modal
import shutil
import pathlib
import tarfile
import tempfile
import websocket
import subprocess
import urllib.request
from urllib.error import URLError
from typing import Dict

from api import Task
import tools
import s3
import utils


DEPLOYMENT_NAME = "comfyui-dev2"

workflows = [
    "txt2img", "txt2img2",
    "SD3", "face_styler",
    "txt2vid", "txt2vid_lora",
    "img2vid", "vid2vid", "style_mixing",
    "video_upscaler", 
    #"xhibit/vton", "xhibit/remix", 
    "moodmix",
    "inpaint"
]

class ComfyUI:

    def _spawn_server(self, port=8188):
        cmd = f"python main.py --dont-print-server --listen --port {port}"
        subprocess.Popen(cmd, shell=True)

    def start(self):
        self.server_address = "127.0.0.1:8189"
        self.client_id = str(uuid.uuid4())
        self._spawn_server(port=8189)
        while not self._is_server_running():
            time.sleep(1)

    def api(
        self, 
        workflow_name: str,
        workflow_path: str,
        tool_path: str,
        args: Dict
    ):
        try:
            tool = tools.load_tool(workflow_name, tool_path)
            print("user args", args)
            workflow = json.load(open(workflow_path, 'r'))
            workflow = inject_args_into_workflow(workflow, tool, args)
            print("workflow after injection")
            print(workflow)
            ws = self._connect_to_server(self.client_id)
            prompt_id = self._queue_prompt(workflow, self.client_id)['prompt_id']
            print("prompt id", prompt_id) 
            outputs = self._get_outputs(ws, prompt_id)
            print("comfyui outputs", outputs)
            output = outputs.get(str(tool.comfyui_output_node_id))
            print("final", output)
            return output
        except Exception as e:
            raise Exception(f"Error running workflow {workflow_name}: {e}")
    
    def _is_server_running(self):
        try:
            url = f"http://{self.server_address}/history/123"
            with urllib.request.urlopen(url) as response:
                return response.status == 200
        except URLError:
            return False

    def _connect_to_server(self, client_id):
        ws = websocket.WebSocket()
        while True:
            try:
                ws.connect(f"ws://{self.server_address}/ws?clientId={client_id}")
                print("Connection established!")
                return ws
            except ConnectionRefusedError:
                print("Server still starting up...")
                time.sleep(1)

    def _queue_prompt(self, prompt, client_id):
        p = {"prompt": prompt, "client_id": client_id}
        data = json.dumps(p).encode('utf-8')
        req = urllib.request.Request("http://{}/prompt".format(self.server_address), data=data)
        return json.loads(urllib.request.urlopen(req).read())

    def _get_history(self, prompt_id):
        with urllib.request.urlopen("http://{}/history/{}".format(self.server_address, prompt_id)) as response:
            return json.loads(response.read())

    def _get_outputs(self, ws, prompt_id):
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message["type"] == "executing":
                    data = message["data"]
                    print("got data", data)
                    print(data.keys())
                    if data.get("prompt_id") == prompt_id:
                        if data["node"] is None:
                            break
            else:
                continue
        outputs = {}
        history = self._get_history(prompt_id)[prompt_id]
        for _ in history['outputs']:
            for node_id in history['outputs']:
                node_output = history['outputs'][node_id]
                if 'images' in node_output:
                    outputs[node_id] = [
                        os.path.join("output", image['subfolder'], image['filename'])
                        for image in node_output['images']
                    ]
                elif 'gifs' in node_output:
                    outputs[node_id] = [
                        os.path.join("output", video['subfolder'], video['filename'])
                        for video in node_output['gifs']
                    ]
        return outputs
        

def install_comfyui():
    snapshot = json.load(open("/root/snapshot.json", 'r'))
    comfyui_commit_sha = snapshot["comfyui"]
    subprocess.run(["git", "init", "."], check=True)
    subprocess.run(["git", "remote", "add", "--fetch", "origin", "https://github.com/comfyanonymous/ComfyUI"], check=True)
    subprocess.run(["git", "checkout", comfyui_commit_sha], check=True)
    subprocess.run(["pip", "install", "xformers!=0.0.18", "-r", "requirements.txt", "--extra-index-url", "https://download.pytorch.org/whl/cu121"], check=True)


def install_custom_nodes():
    snapshot = json.load(open("/root/snapshot.json", 'r'))
    custom_nodes = snapshot["git_custom_nodes"]
    for url, node in custom_nodes.items():
        print(f"Installing custom node {url} with hash {hash}")
        install_custom_node(url, node['hash'])
    post_install_commands = snapshot.get("post_install_commands", [])
    for cmd in post_install_commands:
        os.system(cmd)
    

def install_custom_node(url, hash):
    repo_name = url.split("/")[-1].split(".")[0]
    repo_path = f"custom_nodes/{repo_name}"
    if os.path.exists(repo_path):
        return
    repo = git.Repo.clone_from(url, repo_path)
    repo.submodule_update(recursive=True)    
    repo.git.checkout(hash)
    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.startswith("requirements") and file.endswith((".txt", ".pip")):
                try:
                    requirements_path = os.path.join(root, file)
                    if "with-cupy" in requirements_path: # hack for ComfyUI-Frame-Interpolation, don't use CuPy
                        continue
                    subprocess.run(["pip", "install", "-r", requirements_path], check=True)
                except Exception as e:
                    print(f"Error installing requirements: {e}")


def download_custom_files():
    downloads = json.load(open("/root/downloads.json", 'r'))
    for path, url in downloads.items():
        comfy_path = pathlib.Path("/root") / path
        vol_path = pathlib.Path("/data") / path
        if vol_path.is_file():
            print(f"Skipping download, getting {path} from cache")
        else:
            print(f"Downloading {url} to {vol_path}")
            vol_path.parent.mkdir(parents=True, exist_ok=True)
            utils.download_file(url, vol_path)
            downloads_vol.commit()
        try:
            comfy_path.parent.mkdir(parents=True, exist_ok=True)
            comfy_path.symlink_to(vol_path)
        except Exception as e:
            raise Exception(f"Error linking {comfy_path} to {vol_path}: {e}")
        if not pathlib.Path(comfy_path).exists():
            raise Exception(f"No file found at {comfy_path}")


def test_workflow():
    tool = tools.load_tool(workflow_name, "/root/api.yaml")
    args = json.loads(open("/root/test.json", "r").read())
    args = tools.prepare_args(tool, args)
    comfy = ComfyUI()
    comfy.start()
    output = comfy.api(
        workflow_name,  
        "/root/workflow_api.json", 
        "/root/api.yaml", 
        args
    )
    if not output:
       raise Exception("No output from test")
    print("test output", output)


def inject_embedding_mentions(text, embedding_name):
    reference = f'embedding:{embedding_name}.safetensors'
    text = re.sub(rf'(<{embedding_name}>|{embedding_name})', reference, text, flags=re.IGNORECASE)
    text = re.sub(r'(<concept>)', reference, text, flags=re.IGNORECASE)
    if reference not in text:
        text = f"in the style of {reference}, {text}"
    return text


def transport_lora(
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
        print("Lore bundle already extracted. Skipping.")
    else:
        try:
            with tarfile.open(source_tar, "r:*") as tar:
                tar.extractall(path=destination_folder)
                print("Extraction complete.")
        except Exception as e:
            raise IOError(f"Failed to extract tar file: {e}")

    extracted_files = os.listdir(destination_folder)
    
    # Find the base name X for the files X.safetensors and X_embeddings.safetensors
    base_name = None
    pattern = re.compile(r"^(.+)_embeddings\.safetensors$")
    for file in extracted_files:
        match = pattern.match(file)
        if match:
            base_name = match.group(1)
            break
    
    if base_name is None:
        raise FileNotFoundError("No matching files found for pattern X_embeddings.safetensors.")
    
    lora_filename = f"{base_name}.safetensors"
    embeddings_filename = f"{base_name}_embeddings.safetensors"

    # hack to correct for older lora naming convention
    if str(lora_filename) not in extracted_files:
        print("! Old lora naming convention detected. Correcting...")
        lora_filename = f"{base_name}_lora.safetensors"

    for file in [lora_filename, embeddings_filename]:
        if str(file) not in extracted_files:
            raise FileNotFoundError(f"!! Required file {file} does not exist in the extracted files.")

    if not os.path.exists(loras_folder):
        os.makedirs(loras_folder)
    if not os.path.exists(embeddings_folder):
        os.makedirs(embeddings_folder)

    lora_path = os.path.join(destination_folder, lora_filename)
    embeddings_path = os.path.join(destination_folder, embeddings_filename)

    # copy lora file to loras folder
    lora_filename = lora_filename.replace("_lora.safetensors", ".safetensors")  
    lora_copy_path = os.path.join(loras_folder, lora_filename)
    shutil.copy(lora_path, lora_copy_path)
    print(f"LoRA {lora_path} has been moved to {lora_copy_path}.")

    # copy embedding file to embeddings folder
    embeddings_filename = embeddings_filename.replace("_embeddings.safetensors", ".safetensors") 
    embeddings_copy_path = os.path.join(embeddings_folder, embeddings_filename)
    shutil.copy(embeddings_path, embeddings_copy_path)
    print(f"Embeddings {embeddings_path} has been moved to {embeddings_copy_path}.")
    
    return lora_filename, base_name


def inject_args_into_workflow(workflow, tool, args):
    embedding_trigger = None
    
    # download and transport files
    for param in tool.parameters: 
        if param.type in tools.FILE_TYPES:
            url = args.get(param.name)
            args[param.name] = utils.download_file(url, f"/root/input{url.split('/')[-1]}") if url else None
        
        elif param.type in tools.FILE_ARRAY_TYPES:
            urls = args.get(param.name)
            args[param.name] = [utils.download_file(url, f"/root/input/{url.split('/')[-1]}") if url else None for url in urls] if urls else None
        
        elif param.type == tools.ParameterType.LORA:
            lora_url = args.get(param.name)
            print("lora_url", lora_url)
            if lora_url:
                lora_filename = lora_url.split("/")[-1]
                lora_tarfile = utils.download_file(lora_url, f"/root/downloads/{lora_filename}")
                lora_filename, embedding_trigger = transport_lora(
                    lora_tarfile, 
                    downloads_folder="/root/downloads",
                    loras_folder="/root/models/loras",
                    embeddings_folder="/root/models/embeddings"
                )
                print("set lora to", lora_filename, embedding_trigger)
                args[param.name] = lora_filename        
        
    # inject args
    comfyui_map = {
        param.name: param.comfyui 
        for param in tool.parameters if param.comfyui
    }

    for key, comfyui in comfyui_map.items():
        value = args.get(key)
        if value is None:
            continue

        # if there's a lora, replace mentions with embedding name
        if key == "prompt" and embedding_trigger:
            value = inject_embedding_mentions(value, embedding_trigger)
            print("prompt updated:", value)

        if comfyui.preprocessing is not None:
            if comfyui.preprocessing == "csv":
                value = ",".join(value)

            elif comfyui.preprocessing == "folder":
                print("move to folder")
                temp_subfolder = tempfile.mkdtemp(dir="/root/input")
                print("temp subfolder", temp_subfolder)
                print(value)
                if isinstance(value, list):
                    print("q1")
                    for i, file in enumerate(value):
                        print("q", i)
                        filename = f"{i:06d}_{os.path.basename(file)}"
                        print(filename)
                        new_path = os.path.join(temp_subfolder, filename)
                        shutil.copy(file, new_path)
                else:
                    shutil.copy(value, temp_subfolder)
                value = temp_subfolder

        node_id, field, subfield = str(comfyui.node_id), comfyui.field, comfyui.subfield
        subfields = [s.strip() for s in subfield.split(",")]
        for subfield in subfields:
            print("inject", node_id, field, subfield, " = ", value)
            if node_id not in workflow or field not in workflow[node_id] or subfield not in workflow[node_id][field]:
                raise Exception(f"Node ID {node_id}, field {field}, subfield {subfield} not found in workflow")
            workflow[node_id][field][subfield] = value  

    return workflow


class EdenComfyUI(ComfyUI):
    @modal.build()
    def download(self):
        download_custom_files()
    
    @modal.build()
    def test(self):
        test_workflow()

    @modal.enter()
    def start(self):
        super().start()

    # @modal.web_server(8188, startup_timeout=300)
    # def ui(self):
    #     self._spawn_server()

    # @modal.web_endpoint(method="POST")
    @modal.method()
    def api(self, task: Dict):
        task = Task(**task)
        task.status = "running"
        task.save()
        print(task)
        
        output = super().api(
            workflow_name, 
            "/root/workflow_api.json", 
            "/root/api.yaml", 
            task.args
        )
        
        # if 'error' in output:
        #     return output
        urls = [s3.upload_file(o, png_to_jpg=True) for o in output]
        task.status = "completed"
        task.result = urls
        task.save()


downloads_vol = modal.Volume.from_name(
    "comfy-downloads", 
    create_if_missing=True
)

app = modal.App(
    name=DEPLOYMENT_NAME,
    secrets=[
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("openai"),
        modal.Secret.from_name("mongo-credentials")
    ],
)

for workflow_name in workflows: 
    workflow_dir = pathlib.Path("../workflows") / workflow_name

    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("git", "git-lfs", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1")
        .pip_install("httpx", "tqdm", "websocket-client", "gitpython", "boto3", "requests", "Pillow",
                     "fastapi==0.103.1", "python-magic", "python-dotenv", "pyyaml", "instructor==1.2.6")
        .pip_install("bson")
        .pip_install("pymongo")
        .pip_install("replicate")
        .pip_install("pyjwt")
        .copy_local_file(workflow_dir / "snapshot.json", "/root/snapshot.json")
        .run_function(install_comfyui)
        .run_function(install_custom_nodes, gpu=modal.gpu.A100())        
        .copy_local_file(workflow_dir / "downloads.json", "/root/downloads.json")
        .copy_local_file(workflow_dir / "workflow_api.json", "/root/workflow_api.json")
        .copy_local_file(workflow_dir / "api.yaml", "/root/api.yaml")
        .copy_local_file(workflow_dir / "test.json", "/root/test.json")
        # .pip_install("bson==0.5.10", "pymongo==4.8.0")
        #pymongo 4.8.0, 0.5.10
    )

    # with image.imports():
    #     from api import Task
    #     import tools
    #     import s3
    
    cls = type(workflow_name, (EdenComfyUI,), {})
    
    gpu = modal.gpu.A100(size="80GB") if workflow_name == "xhibit/vton" else modal.gpu.A100()

    globals()[workflow_name] = app.cls(
        gpu=gpu,
        allow_concurrent_inputs=5,
        image=image,
        volumes={"/data": downloads_vol},
        timeout=1800,
        container_idle_timeout=60,
    )(cls)
