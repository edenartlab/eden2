import os
import git
import json
import pathlib
import websocket
import subprocess
import uuid
import time
import modal
import urllib.request
from urllib.error import URLError
from typing import Dict
from utils import download_file


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
        tool = tools.load_tool(workflow_name, tool_path)
        workflow_args = tools.prepare_args(tool, args)
        workflow = json.load(open(workflow_path, 'r'))
        workflow = tools.inject_args_into_workflow(workflow, tool, workflow_args)
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
            print(f"Downloading {url} to {vol_path.parent}")
            vol_path.parent.mkdir(parents=True, exist_ok=True)
            download_file(url, vol_path.parent)
            downloads_vol.commit()

        print("sym link from", comfy_path, "to", vol_path)
        try:
            comfy_path.parent.mkdir(parents=True, exist_ok=True)
            comfy_path.symlink_to(vol_path)
        except Exception as e:
            print("symlink failed", e)
            if not pathlib.Path(comfy_path).exists():
                raise Exception(f"No f333ile found at {comfy_path}")
        if not pathlib.Path(comfy_path).exists():
            raise Exception(f"No file found at {comfy_path}")


def test_workflow():
    args = json.loads(open("/root/test.json", "r").read())
    print(args)
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
    print("output", output)

class ModalComfyUI(ComfyUI):
    @modal.build()
    def build(self):
        download_custom_files()
        test_workflow()

    @modal.enter()
    def start(self):
        super().start()

    # @modal.web_server(8188, startup_timeout=300)
    # def ui(self):
    #     self._spawn_server()

    @modal.method()
    def api(self, args: Dict):
        output = super().api(
            workflow_name, 
            "/root/workflow_api.json", 
            "/root/api.yaml", 
            args
        )
        print(output)
        if 'error' in output:
            return output
        urls = [upload_file(o, png_to_jpg=True) for o in output]
        return {"urls": urls}


downloads_vol = modal.Volume.from_name("comfy-downloads", create_if_missing=True)

app = modal.App(
    name="comfyui",
    secrets=[
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("openai")
    ],
)

workflows = ["txt2img", "txt2vid", "img2vid", "style_mixing", "vid2vid", "xhibit"]

for workflow_name in workflows: 
    workflow_dir = pathlib.Path("../workflows") / workflow_name

    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("git", "git-lfs", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1")
        .pip_install("httpx", "tqdm", "websocket-client", "gitpython", "boto3", 
                     "fastapi==0.103.1", "python-magic", "python-dotenv", "pyyaml")
        .copy_local_file(workflow_dir / "snapshot.json", "/root/snapshot.json")
        .copy_local_file(workflow_dir / "downloads.json", "/root/downloads.json")
        .copy_local_file(workflow_dir / "workflow_api.json", "/root/workflow_api.json")
        .copy_local_file(workflow_dir / "api.yaml", "/root/api.yaml")
        .copy_local_file(workflow_dir / "test.json", "/root/test.json")
        .copy_local_file("utils.py", remote_path="/root/utils.py")
        .copy_local_file("s3.py", remote_path="/root/s3.py")
        .copy_local_file("endpoint.py", remote_path="/root/endpoint.py")
        .run_function(install_comfyui)
        .run_function(install_custom_nodes, gpu=modal.gpu.A100())        
        # .run_function(download_custom_files)
        # .run_function(test_workflow, gpu=modal.gpu.A100())
    )

    with image.imports():
        import endpoint as tools
        from s3 import upload_file
        from utils import download_file

    cls = type(workflow_name, (ModalComfyUI,), {})
    
    globals()[workflow_name] = app.cls(
        # gpu=modal.gpu.A100(size="80GB"),
        gpu=modal.gpu.A100(),
        allow_concurrent_inputs=1,
        image=image,
        volumes={"/data": downloads_vol},
        timeout=600,
        container_idle_timeout=300,
    )(cls)
