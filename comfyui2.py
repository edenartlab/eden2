from urllib.error import URLError
from datetime import datetime
from bson import ObjectId
import os
import re
import git
import time
import json
import modal
import shutil
import urllib
import tarfile
import pathlib
import tempfile
import subprocess

from models import Task, models
import tool2 as tool
import utils


GPUs = {
    "A100": modal.gpu.A100(),
    "A100-80GB": modal.gpu.A100(size="80GB")
}

prod_env = os.getenv("APP", "STAGE").lower()
env_name = os.getenv("ENV").lower()

available_envs = ["txt2img", "video", "audio", "flux"]
if env_name not in available_envs:
    raise Exception(f"Invalid environment: {env_name}. Available options: {', '.join(available_envs)}")
if prod_env not in ["prod", "stage"]:
    raise Exception(f"Invalid environment: {prod_env}. Must be PROD or STAGE")

app_name = "comfyui" if prod_env == "prod" else "comfyui-dev"
app_name = f"{app_name}-{env_name}"


def install_comfyui():
    snapshot = json.load(open("/root/env/snapshot.json", 'r'))
    comfyui_commit_sha = snapshot["comfyui"]
    subprocess.run(["git", "init", "."], check=True)
    subprocess.run(["git", "remote", "add", "--fetch", "origin", "https://github.com/comfyanonymous/ComfyUI"], check=True)
    subprocess.run(["git", "checkout", comfyui_commit_sha], check=True)
    subprocess.run(["pip", "install", "xformers!=0.0.18", "-r", "requirements.txt", "--extra-index-url", "https://download.pytorch.org/whl/cu121"], check=True)


def install_custom_nodes():
    snapshot = json.load(open("/root/env/snapshot.json", 'r'))
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


image = (
    modal.Image.debian_slim(python_version="3.11")
    .env({"APP": prod_env, "ENV": env_name})
    .apt_install("git", "git-lfs", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1", "ffmpeg")
    .pip_install(
        "httpx", "tqdm", "websocket-client", "gitpython", "boto3",
        "requests", "Pillow", "fastapi==0.103.1", "python-magic", "replicate", 
        "python-dotenv", "pyyaml", "instructor==1.2.6", "torch==2.3.1", "torchvision", "packaging",
        "torchaudio", "pydub", "moviepy", "accelerate")
    .pip_install("bson").pip_install("pymongo") 
    .copy_local_dir(f"../workflows/environments/{env_name}", "/root/env")
    .run_function(install_comfyui)
    .run_function(install_custom_nodes, gpu=modal.gpu.A100())
)

gpu = modal.gpu.A100()

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

@app.cls(
    image=image,
    gpu=gpu,
    volumes={"/data": downloads_vol},
    concurrency_limit=3,
    container_idle_timeout=60,
    timeout=60,
)
class ComfyUI:
    
    def _start(self, port=8188):
        self.server_address = f"127.0.0.1:{port}"
        cmd = f"python main.py --dont-print-server --listen --port {port}"
        subprocess.Popen(cmd, shell=True)
        while not self._is_server_running():
            time.sleep(1)

    def _execute(self, workflow_name: str, args: dict):
        print("args", workflow_name, args)
        tool_path = f"/root/env/workflows/{workflow_name}"
        tool_ = tool.load_tool(tool_path)
        workflow = json.load(open(f"{tool_path}/workflow_api.json", 'r'))
        workflow = self._inject_args_into_workflow(workflow, tool_, args)
        prompt_id = self._queue_prompt(workflow)['prompt_id']
        outputs = self._get_outputs(prompt_id)
        print("comfyui outputs", outputs)
        output = outputs.get(str(tool_.comfyui_output_node_id))
        if not output:
            raise Exception(f"No output found at output node") 
        return output

    @modal.method()
    def run(self, workflow_name: str, args: dict):
        tool_ = tool.load_tool(f"/root/env/workflows/{workflow_name}")
        output = self._execute(workflow_name, args)
        result = tool_.process_output(output)
        return result

    @modal.method()
    def api(self, task: dict):
        task = Task(**task)
        tool_ = tool.load_tool(f"/root/env/workflows/{task.workflow}")

        start_time = datetime.utcnow()
        queue_time = (start_time - task.createdAt).total_seconds()

        task.update({
            "status": "running",
            "performance": {"queueTime": queue_time}
        })
        
        try:
            output = self._execute(task.workflow, task.args)
            result = tool_.process_output(output)            
            task_update = {
                "status": "completed", 
                "result": result
            }
        
        except Exception as e:
            print("Task failed", e)
            task_update = {"status": "failed", "error": str(e)}
        
        run_time = datetime.utcnow() - start_time
        task_update["performance.runTime"] = run_time.total_seconds()
        task.update(task_update)

        return task_update

    @modal.enter()
    def enter(self):
        self._start()

    @modal.build()
    def download(self):
        downloads = json.load(open("/root/env/downloads.json", 'r'))
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

    @modal.build()
    def test(self):
        t1 = time.time()
        self._start()
        t2 = time.time()
        results = {"_performance": {"launch": t2 - t1}}
        workflows_dir = pathlib.Path("/root/env/workflows")
        workflow_names = [f.name for f in workflows_dir.iterdir() if f.is_dir()]
        for workflow in workflow_names:
            tool_ = tool.load_tool(f"/root/env/workflows/{workflow}")
            t1 = time.time()
            output = self._execute(workflow, tool_.test_args)
            if not output:
                raise Exception(f"No output from {workflow} test")
            result = tool_.process_output(output)
            t2 = time.time()
            results[workflow] = result
            results["_performance"][workflow] = t2 - t1
        t3 = time.time()
        self._start(port=8194)
        t4 = time.time()
        results["_performance"]["launch2"] = t4 - t3
        with open("_test_results_.json", "w") as f:
            json.dump(results, f, indent=4)

    @modal.method()
    def print_test_results(self):
        with open("_test_results_.json", "r") as f:
            results = json.load(f)
        print("\n\n\n============ Test Results ============")
        print(json.dumps(results, indent=4))

    def _is_server_running(self):
        try:
            url = f"http://{self.server_address}/history/123"
            with urllib.request.urlopen(url) as response:
                return response.status == 200
        except URLError:
            return False

    def _queue_prompt(self, prompt):
        data = json.dumps({"prompt": prompt}).encode('utf-8')
        req = urllib.request.Request("http://{}/prompt".format(self.server_address), data=data)
        return json.loads(urllib.request.urlopen(req).read())

    def _get_history(self, prompt_id):
        with urllib.request.urlopen("http://{}/history/{}".format(self.server_address, prompt_id)) as response:
            return json.loads(response.read())

    def _get_outputs(self, prompt_id):        
        while True:
            outputs = {}
            history = self._get_history(prompt_id)
            if prompt_id not in history:
                time.sleep(1)
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

    def _inject_embedding_mentions(self, text, embedding_name):
        reference = f'embedding:{embedding_name}.safetensors'
        text = re.sub(rf'(<{embedding_name}>|{embedding_name})', reference, text, flags=re.IGNORECASE)
        text = re.sub(r'(<concept>)', reference, text, flags=re.IGNORECASE)
        if reference not in text:
            text = f"in the style of {reference}, {text}"
        return text

    def _transport_lora(
        self,
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

    def _url_to_filename(self, url):
        filename = url.split('/')[-1]
        filename = re.sub(r'\?.*$', '', filename)
        max_length = 255
        if len(filename) > max_length: # ensure filename is not too long
            name, ext = os.path.splitext(filename)
            filename = name[:max_length - len(ext)] + ext
        return filename    

    def _inject_args_into_workflow(self, workflow, tool_, args):
        embedding_trigger = None
        
        # download and transport files
        for param in tool_.parameters: 
            if param.type in tool.FILE_TYPES:
                url = args.get(param.name)
                args[param.name] = utils.download_file(url, f"/root/input{self._url_to_filename(url)}") if url else None
            
            elif param.type in tool.FILE_ARRAY_TYPES:
                urls = args.get(param.name)
                args[param.name] = [
                    utils.download_file(url, f"/root/input/{self._url_to_filename(url)}") if url else None 
                    for url in urls
                ] if urls else None
            
            elif param.type == tool.ParameterType.LORA:
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
                print("LORA URL 2", lora_url)
                # if lora_url:
                lora_filename, embedding_trigger = self._transport_lora(
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
                value = self._inject_embedding_mentions(value, embedding_trigger)
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


@app.local_entrypoint()
def run():
    comfyui = ComfyUI()
    comfyui.print_test_results.remote()
