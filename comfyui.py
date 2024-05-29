# generalize for all endpoints
# run test job at end of build
# run test job on command
# verifying ui
# dev environment (UI)

import os
import git
import json
import httpx
import pathlib
import websocket
import subprocess
import uuid
import time
import modal
import urllib.request
from urllib.error import URLError
from tqdm import tqdm
from typing import Dict

import endpoint as tools
from utils import download_file


class ComfyUI:

    def _run_comfyui_server(self, port=8188):
        cmd = f"python main.py --dont-print-server --listen --port {port}"
        subprocess.Popen(cmd, shell=True)

    def start_comfyui(self):
        self.server_address = "127.0.0.1:8189"
        self.client_id = str(uuid.uuid4())
        self._run_comfyui_server(port=8189)
        while not self._is_server_running():
            time.sleep(1)

    def api(self, workflow_name: str, args: Dict):
        tool = tools.load_tool(workflow_name)
        workflow_args = tools.prepare_args(tool, args)
        workflow = tools.inject_args_into_workflow(workflow_name, workflow_args)
        ws = self._connect_to_server(self.client_id)
        prompt_id = self._queue_prompt(workflow, self.client_id)['prompt_id']
        outputs = self._get_outputs(ws, prompt_id)
        output = outputs.get(str(tool.comfyui_output_node_id))
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
        while True:
            out = ws.recv()
            if isinstance(out, str):
                message = json.loads(out)
                if message["type"] == "executing":
                    data = message["data"]
                    if data["prompt_id"] == prompt_id:
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
    
    # def _download_to_comfyui(self, url, path):
    #     local_filepath = pathlib.Path(path)
    #     local_filepath.parent.mkdir(parents=True, exist_ok=True)
    #     print(f"Downloading {url} ... to {local_filepath}")
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

    # def _install_custom_node(self, url, hash):
    #     repo_name = url.split("/")[-1].split(".")[0]
    #     repo_path = f"custom_nodes/{repo_name}"
    #     if os.path.exists(repo_path):
    #         return
    #     repo = git.Repo.clone_from(url, repo_path)
    #     repo.submodule_update(recursive=True)    
    #     repo.git.checkout(hash)
    #     for root, _, files in os.walk(repo_path):
    #         for file in files:
    #             if file.startswith("requirements") and file.endswith((".txt", ".pip")):
    #                 try:
    #                     requirements_path = os.path.join(root, file)
    #                     subprocess.run(["pip", "install", "-r", requirements_path], check=True)
    #                 except Exception as e:
    #                     print(f"Error installing requirements: {e}")


# def download_file(url, path):
#     local_filepath = pathlib.Path(path)
#     local_filepath.parent.mkdir(parents=True, exist_ok=True)
#     print(f"Downloading {url} ... to {local_filepath}")
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
                    subprocess.run(["pip", "install", "-r", requirements_path], check=True)
                except Exception as e:
                    print(f"Error installing requirements: {e}")






#endpoint_name = "style_mixing"
workflow_name = "vid2vid"
workflows_dir = "../workflows"
workflow_dir = pathlib.Path(workflows_dir) / workflow_name


def install_comfyui():
    snapshot = json.load(open("/root/snapshot.json", 'r'))
    comfyui_commit_sha = snapshot["comfyui"]
    subprocess.run(["git", "init", "."], check=True)
    subprocess.run(["git", "remote", "add", "--fetch", "origin", "https://github.com/comfyanonymous/ComfyUI"], check=True)
    subprocess.run(["git", "checkout", comfyui_commit_sha], check=True)
    subprocess.run(["pip", "install", "xformers!=0.0.18", "-r", "requirements.txt", "--extra-index-url", "https://download.pytorch.org/whl/cu121"], check=True)

def prepare_custom_nodes_and_downloads():
    snapshot = json.load(open("/root/snapshot.json", 'r'))
    custom_nodes = snapshot["git_custom_nodes"]
    for url, node in custom_nodes.items():
        print(f"Installing custom node {url} with hash {hash}")
        install_custom_node(url, node['hash'])
    downloads = json.load(open("/root/downloads.json", 'r'))
    for path, url in downloads.items():
        path = str(pathlib.Path(path).parent)
        print(f"Downloading {url} to {path}")
        download_file(url, path)

def test_workflow():
    comfy = ComfyUI()
    comfy.start_comfyui()
    args = json.loads(open("/root/test.json", "r").read())
    output = comfy.api(workflow_name, args)
    print(output)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "git-lfs", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1")
    .pip_install("httpx", "tqdm", "websocket-client", "gitpython", "boto3", "fastapi==0.103.1", "python-magic", "python-dotenv", "pyyaml") 
    .copy_local_file(workflow_dir / "snapshot.json", "/root/snapshot.json")
    .copy_local_file(workflow_dir / "downloads.json", "/root/downloads.json")
    .copy_local_file(workflow_dir / "workflow_api.json", "/root/workflow_api.json")
    .copy_local_file(workflow_dir / "api.yaml", "/root/api.yaml")
    .copy_local_file(workflow_dir / "test.json", "/root/test.json")
    .copy_local_file("utils.py", remote_path="/root/utils.py")
    .copy_local_file("s3.py", remote_path="/root/s3.py")
    .copy_local_file("endpoint.py", remote_path="/root/endpoint.py")
    .run_function(install_comfyui)
    .run_function(prepare_custom_nodes_and_downloads, gpu=modal.gpu.Any())
    .run_function(test_workflow, gpu=modal.gpu.A100())
    # .run_function(install_nodes_and_downloads, gpu=modal.gpu.Any())
)

app = modal.App(
    name="comfyui",
    secrets=[
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("openai")
    ],
)

with image.imports():
    import endpoint as tools
    from s3 import upload_file
    from utils import download_file


@app.cls(
    allow_concurrent_inputs=10,
    gpu="any",
    image=image,
    timeout=600,
    container_idle_timeout=600,
    mounts=[
        modal.Mount.from_local_file(
            workflow_dir / "workflow_api.json",
            "/root/workflow_api.json",
        )
    ],
)
class ModalComfyUI(ComfyUI):
    @modal.build()
    def build(self):
        pass

    @modal.enter()
    def start_comfyui(self):
        super().start_comfyui()

    # @modal.web_server(8188, startup_timeout=30)
    # def ui(self):
    #     self._run_comfyui_server()

    @modal.web_endpoint(method="POST")
    def api(self, args: Dict):
        output = super().api(workflow_name, args)
        if 'error' in output:
            return output
        urls = [upload_file(o, png_to_jpg=True) for o in output]
        return {"urls": urls}







# def download_to_comfyui(url, path):
#     local_filepath = pathlib.Path(path)
#     local_filepath.parent.mkdir(parents=True, exist_ok=True)
#     print(f"Downloading {url} ... to {local_filepath}")
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

# def install_custom_node2(url, hash):
#     print("install_custom_node2 A")
#     path = "custom_nodes"
#     subprocess.run(["git", "clone", url, "--recursive"], cwd=path)
#     print("install_custom_node2 B")
#     # Determine the repository name from the URL
#     repo_name = url.split("/")[-1].split(".")[0]
#     repo_path = f"{path}/{repo_name}"
#     print("install_custom_node2 C")

#     # Checkout the specific commit hash
#     subprocess.run(["git", "checkout", hash], cwd=repo_path)
#     print("install_custom_node2 D")

#     # Pip install requirements.txt if it exists in the custom node
#     if os.path.isfile(f"{repo_path}/requirements.txt"):
#         print("install_custom_node2 E")
#         print("Installing custom node requirements...")
#         subprocess.run(
#             ["pip", "install", "-r", "requirements.txt"], cwd=repo_path
#         )
#         print("install_custom_node2 F")
#     print("install_custom_node2 G")

# def d_install_custom_node(url, hash):
#     repo_name = url.split("/")[-1].split(".")[0]
#     repo_path = f"custom_nodes/{repo_name}"
#     if os.path.exists(repo_path):
#         return
#     repo = git.Repo.clone_from(url, repo_path)
#     repo.submodule_update(recursive=True)    
#     repo.git.checkout(hash)
#     for root, _, files in os.walk(repo_path):
#         for file in files:
#             if file.startswith("requirements") and file.endswith((".txt", ".pip")):
#                 try:
#                     requirements_path = os.path.join(root, file)
#                     subprocess.run(["pip", "install", "-r", requirements_path], check=True)
#                 except Exception as e:
#                     print(f"Error installing requirements: {e}")

