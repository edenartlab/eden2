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
import argparse
import websocket
import subprocess
import urllib.request
from bson import ObjectId
from urllib.error import URLError
from datetime import datetime
from typing import Dict

import tool
import s3
import utils

APP_NAME_PROD  = "comfyui"
APP_NAME_STAGE = "comfyui-dev"
app_name = APP_NAME_STAGE

GPUs = {
    "A100": modal.gpu.A100(),
    "A100-80GB": modal.gpu.A100(size="80GB")
}

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
        tool_ = tool.load_tool(tool_path)
        print("user args", args)
        workflow = json.load(open(workflow_path, 'r'))
        workflow = inject_args_into_workflow(workflow, tool_, args)
        print("workflow after injection")
        print(workflow)
        # ws = self._connect_to_server(self.client_id)
        ws = None
        prompt_id = self._queue_prompt(workflow, self.client_id)['prompt_id']
        print("prompt id", prompt_id) 
        #outputs = self._get_outputs(ws, prompt_id)
        outputs = self._get_outputs(ws, prompt_id)
        print("comfyui outputs", outputs)
        output = outputs.get(str(tool_.comfyui_output_node_id))
        print("final", output)
        if not output:
            raise Exception(f"No output found at node {str(tool_.comfyui_output_node_id)}") 
        return output
    
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
        print("comfy start")
        
        # ws.settimeout(60) 
        # try:
        #     while True:
        #         try:
        #             out = ws.recv()
        #             # print("comfgo, recv time=", time.time())
        #             if isinstance(out, str):
        #                 message = json.loads(out)
        #                 if message["type"] == "executing":
        #                     data = message["data"]
        #                     if data.get("prompt_id") == prompt_id:
        #                         if data["node"] is None:
        #                             break
        #             else:
        #                 continue
        #         except websocket.WebSocketTimeoutException:
        #             print("comfgo, WebSocket timeout, retrying...")
        #             continue
        # except (websocket.WebSocketConnectionClosedException, websocket.WebSocketException) as e:
        #     print(f"comfgo, WebSocket error: {e}")
        #     raise Exception("WebSocket connection error")

        while True:
            outputs = {}
            history = self._get_history(prompt_id)
            if prompt_id not in history:
                time.sleep(2)
                continue
            history = history[prompt_id]                        
            status = history["status"]
            status_str = status.get("status_str")
            if status_str == "error":
                messages = status.get("messages")
                errors = [                    
                    f"ComfyUI Error: {v.get('node_type')} {v.get('exception_type')}, {v.get('exception_message')}"
                    for k, v in messages if k == "execution_error"
                ]
                error_str = ", ".join(errors)
                print("error", error_str)
                raise Exception(error_str)
            
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
            
            print("comfy outputs", outputs)

            if not outputs:
                raise Exception("No outputs found")
            
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
    tool_ = tool.load_tool("/root", name=workflow_name)
    args = json.loads(open("/root/test.json", "r").read())
    args = tool_.prepare_args(args)
    comfy = ComfyUI()
    comfy.start()
    output = comfy.api(
        workflow_name,  
        "/root/workflow_api.json", 
        "/root", 
        args
    )
    if not output:
       raise Exception("No output from test")
    print("test output", output)
    return output


def inject_embedding_mentions(text, embedding_name):
    reference = f'embedding:{embedding_name}.safetensors'
    text = re.sub(rf'(<{embedding_name}>|{embedding_name})', reference, text, flags=re.IGNORECASE)
    text = re.sub(r'(<concept>)', reference, text, flags=re.IGNORECASE)
    if reference not in text:
        text = f"in the style of {reference}, {text}"
    return text


def transport_lora(
    lora_url: str,
    downloads_folder: str,
    loras_folder: str,
    embeddings_folder: str,
):
    print("tl download lora", lora_url)
    if not re.match(r'^https?://', lora_url):
        raise ValueError(f"Lora URL Invalid: {lora_url}")
    
    lora_filename = lora_url.split("/")[-1]    
    name = lora_filename.split(".")[0]
    destination_folder = os.path.join(downloads_folder, name)
    print("tl destination folder", destination_folder)

    if os.path.exists(destination_folder):
        print("Lora bundle already extracted. Skipping.")
    else:
        try:
            lora_tarfile = utils.download_file(lora_url, f"/root/downloads/{lora_filename}")
            if not os.path.exists(lora_tarfile):
                raise FileNotFoundError(f"The LoRA tar file {lora_tarfile} does not exist.")
            with tarfile.open(lora_tarfile, "r:*") as tar:
                tar.extractall(path=destination_folder)
                print("Extraction complete.")
        except Exception as e:
            raise IOError(f"Failed to extract tar file: {e}")

    extracted_files = os.listdir(destination_folder)
    print("tl, extracted files", extracted_files)
    
    # Find the base name X for the files X.safetensors and X_embeddings.safetensors
    base_name = None
    pattern = re.compile(r"^(.+)_embeddings\.safetensors$")
    for file in extracted_files:
        match = pattern.match(file)
        if match:
            base_name = match.group(1)
            break

    print("tl, base name", base_name)
    
    if base_name is None:
        raise FileNotFoundError("No matching files found for pattern X_embeddings.safetensors.")
    
    lora_filename = f"{base_name}.safetensors"
    embeddings_filename = f"{base_name}_embeddings.safetensors"

    # hack to correct for older lora naming convention
    if str(lora_filename) not in extracted_files:
        print("Old lora naming convention detected. Correcting...")
        lora_filename = f"{base_name}_lora.safetensors"
        print("tl, old lora filename", lora_filename)

    for file in [lora_filename, embeddings_filename]:
        if str(file) not in extracted_files:
            raise FileNotFoundError(f"Required file {file} does not exist in the extracted files.")

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

def url_to_filename(url):
    filename = url.split('/')[-1]
    filename = re.sub(r'\?.*$', '', filename)
    max_length = 255
    if len(filename) > max_length: # ensure filename is not too long
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext)] + ext
    return filename    

def inject_args_into_workflow(workflow, tool_, args):
    embedding_trigger = None
    
    # download and transport files
    for param in tool_.parameters: 
        if param.type in tool.FILE_TYPES:
            url = args.get(param.name)
            args[param.name] = utils.download_file(url, f"/root/input{url_to_filename(url)}") if url else None
        
        elif param.type in tool.FILE_ARRAY_TYPES:
            urls = args.get(param.name)
            args[param.name] = [
                utils.download_file(url, f"/root/input/{url_to_filename(url)}") if url else None 
                for url in urls
            ] if urls else None
        
        elif param.type == tool.ParameterType.LORA:
            

            print("PARAM NAME", param.name)
            lora_id = args.get(param.name)
            print("LORA ID", lora_id)
            if not lora_id:
                continue

            lora = models.find_one({"_id": ObjectId(lora_id)})
            print("LORA", lora)
            if not lora:
                raise Exception(f"Lora {lora_id} not found")

            lora_url = lora.get("checkpoint")
            print("LORA URL", lora_url)
            if not lora_url:
                raise Exception(f"Lora {lora_id} has no checkpoint")
            
            # lora_url = args.get(param.name)
            print("LORA UR!!!", lora_url)
            # if lora_url:
            lora_filename, embedding_trigger = transport_lora(
                lora_url, 
                downloads_folder="/root/downloads",
                loras_folder="/root/models/loras",
                embeddings_folder="/root/models/embeddings"
            )
            args[param.name] = lora_filename        
        
    # inject args
    comfyui_map = {
        param.name: param.comfyui 
        for param in tool_.parameters if param.comfyui
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
                temp_subfolder = tempfile.mkdtemp(dir="/root/input")
                if isinstance(value, list):
                    for i, file in enumerate(value):
                        filename = f"{i:06d}_{os.path.basename(file)}"
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
    
    def _run(self, args: Dict):
        output = super().api(
            workflow_name, 
            "/root/workflow_api.json", 
            "/root", 
            args
        )
        print(output)
        # if 'error' in output:
        #     return output
        urls = [s3.upload_file(o, png_to_jpg=True) for o in output]
        return urls

    @modal.method()
    def execute(self, args: Dict):
        return self._run(args)

    @modal.method()
    def api(self, task: Dict):
        task = Task(**task)
        
        start_time = datetime.utcnow()
        queue_time = (start_time - task.createdAt).total_seconds()

        task.update({
            "status": "running",
            "performance": {"queueTime": queue_time}
        })
        
        try:
            output = self._run(task.args)
            task_update = {"status": "completed", "result": output}
        except Exception as e:
            task_update = {"status": "failed", "error": str(e)}
        
        run_time = datetime.utcnow() - start_time
        task_update["performance.runTime"] = run_time.total_seconds()

        task.update(task_update)


if modal.is_local():
    parser = argparse.ArgumentParser(description="Serve or deploy ComfyUI workflows to Modal")
    subparsers = parser.add_subparsers(dest="method", required=True)
    parser_test = subparsers.add_parser("test", help="Test ComfyUI workflows")
    parser_test.add_argument("--workflows", type=str, help="Which workflows to deploy (comma-separated)", default="_all_")
    parser_deploy = subparsers.add_parser("deploy", help="Deploy to Modal")
    parser_deploy.add_argument("--production", action='store_true', help="Deploy to production (otherwise staging)")
    args = parser.parse_args()

    import tool
    workflows = tool.get_tools("../workflows", exclude=["_dev"]) | tool.get_tools("../private_workflows")
    # workflows = {"txt2img": workflows["txt2img"], "SD3": workflows["SD3"]}
    selected_workflows = args.workflows.split(",") if args.method == "test" and args.workflows != "_all_" else workflows.keys()
    selected_workflows = [w for w in selected_workflows]
    missing_workflows = [w for w in selected_workflows if w not in workflows]
    if missing_workflows:
        raise ValueError(f"Workflows {', '.join(missing_workflows)} not found.")
    workflows = {key: workflows[key] for key in selected_workflows}

    if args.method == "deploy" and args.production:
        app_name = APP_NAME_PROD
        confirm = input(f"Warning: this will deploy all of the following pipelines to Modal App {app_name}: {list(workflows.keys())}\n\nThis will overwrite all existing deployments. Are you sure you want to do this?  (y/n): ")
        if confirm.lower() != "y":
            print("Aborting deployment.")
            raise SystemExit

else:    
    workflows = [
        "txt2img", "txt2img2", "SD3", "face_styler",
        "txt2vid", "txt2vid_lora", "img2vid", "img2vid_museV", "vid2vid_sd15", "vid2vid_sdxl", 
        "style_mixing", "video_upscaler", 
        "moodmix", "inpaint", "background_removal",
    ]
    private_workflows = [
        "xhibit/vton", "xhibit/remix", "beeple_ai",
    ]
    workflows = workflows + private_workflows


downloads_vol = modal.Volume.from_name(
    "comfy-downloads", 
    create_if_missing=True
)

app = modal.App(
    name=app_name,
    secrets=[
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("openai"),
        modal.Secret.from_name("mongo-credentials")
    ]
)

for workflow_name in workflows: 
    workflows_root = pathlib.Path("../workflows")
    if workflow_name in ["xhibit/vton", "xhibit/remix", "beeple_ai"]:
        workflows_root = pathlib.Path("../private_workflows")
    workflow_dir = workflows_root / workflow_name
    
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("git", "git-lfs", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1")
        .pip_install("httpx", "tqdm", "websocket-client", "gitpython", "boto3",
                     "requests", "Pillow", "fastapi==0.103.1", "python-magic", "replicate", 
                     "python-dotenv", "pyyaml", "instructor==1.2.6", "torch==2.3.1", "torchvision", "packaging",
                     "torchaudio", "bson")#, "bson", "pymongo")
        .pip_install("bson").pip_install("pymongo") 
        .copy_local_file(workflow_dir / "snapshot.json", "/root/snapshot.json")
        .run_function(install_comfyui)
        .run_function(install_custom_nodes, gpu=modal.gpu.A100())        
        .copy_local_file(workflow_dir / "downloads.json", "/root/downloads.json")
        .copy_local_file(workflow_dir / "workflow_api.json", "/root/workflow_api.json")
        .copy_local_file(workflow_dir / "api.yaml", "/root/api.yaml")
        .copy_local_file(workflow_dir / "test.json", "/root/test.json")
        .env({"ENV": "PROD" if app_name == APP_NAME_PROD else "STAGE"})
    )

    with image.imports():
        from models import Task, models

    gpu = modal.gpu.A100()
    if modal.is_local():
        gpu = GPUs[workflows[workflow_name].gpu]
    
    cls = type(workflow_name, (EdenComfyUI,), {})
    
    globals()[workflow_name] = app.cls(
        gpu=gpu,
        # allow_concurrent_inputs=5,
        concurrency_limit=3,
        image=image,
        volumes={"/data": downloads_vol},
        timeout=1800,
        container_idle_timeout=60
    )(cls)


if __name__ == "__main__":
    if args.method == "test":
        from modal.cli.run import serve
        filepath = os.path.abspath(__file__)
        serve(filepath, timeout=600, env=None)
    elif args.method == "deploy":
        from modal.runner import deploy_app
        deploy_app(app, name=app_name)
    