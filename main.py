import uuid
import modal
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

snapshots = ["txt2img", "txt2vid_lcm", "steerable_motion", "img2vid"]
# snapshots = ["txt2img"]

app = modal.App(
    name="eden-comfyui",
    secrets=[
        modal.Secret.from_name("s3-credentials")
    ],
)

class ComfyUIServerBase:
    @modal.enter()
    def startup(self):
        start = timer()
        self.comfyui = ComfyUI()
        self.comfyui.setup()
        end = timer()
        print("Boot ComfyUI time:", end - start)

    @modal.exit()
    def shutdown(self):
        self.comfyui.stop_server()

    @modal.method()
    def run(self, workflow_file, endpoint_file, config, client_id):
        outputs = self.comfyui.run_workflow(workflow_file, endpoint_file, config, client_id)
        urls = [upload_file(output, png_to_jpg=True) for output in outputs]
        return {"urls": urls}


ComfyUIServers = {}
for snapshot in snapshots:
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("git", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1")
        .run_commands(
            "echo 12345 && pip install git+https://github.com/edenartlab/comfyui_service",
        )
        .copy_local_dir("snapshots", remote_path="/root/snapshots")
        .copy_local_dir("workflows", remote_path="/root/workflows")
        #.copy_local_file("install.py", remote_path="/root/install.py")
        .run_commands(
            f"cd /root && comfyui_service install --snapshot snapshots/{snapshot}.json --workflow workflows/{snapshot}.json --downloads snapshots/_downloads.json --comfyui-home /root/ComfyUI",
            gpu=modal.gpu.Any()
        )
        .run_commands(
            "pip install boto3 fastapi==0.103.1"
        )
        .copy_local_dir("endpoints", remote_path="/root/endpoints")
        # .copy_local_file("comfyui.py", remote_path="/root/comfyui.py")
        # .copy_local_file("configs.py", remote_path="/root/configs.py")
        .copy_local_file("s3.py", remote_path="/root/s3.py")
        # .copy_local_file("test.py", remote_path="/root/test.py")
        .run_commands(
            f'cd /root && comfyui_service run --endpoint endpoints/{snapshot}.yaml --workflow workflows/{snapshot}.json --comfyui-home /root/ComfyUI',
            gpu=modal.gpu.Any()
        )
    ) 

    with image.imports():
        from comfyui_service import ComfyUI
        from s3 import upload_file
        from timeit import default_timer as timer

    cls_name = f"ComfyUIServer_{snapshot}"
    cls = type(cls_name, (ComfyUIServerBase,), {})
    
    # Decorate the class with @app.cls
    decorated_cls = app.cls(
        gpu=modal.gpu.A100(), 
        container_idle_timeout=30, 
        image=image
    )(cls)
    
    # Add the class to the global namespace
    globals()[cls_name] = decorated_cls

    # Create an instance of the class and add it to ComfyUIServers
    ComfyUIServers[snapshot] = decorated_cls()


# web_app = FastAPI()

# class WorkflowRequest(BaseModel):
#     workflow: str
#     config: Dict[str, Any]
#     client_id: Optional[str] = None

# @app.function()
# @web_app.post("/create")
# async def run_workflow(request: WorkflowRequest):
#     if request.workflow not in ComfyUIServers:
#         raise HTTPException(status_code=400, detail="Invalid workflow")

#     if request.client_id is None:
#         client_id = str(uuid.uuid4())

#     workflow_file = f"workflows/{request.workflow}.json"
#     endpoint_file = f"endpoints/{request.workflow}.yaml"

#     comfyui = ComfyUIServers[request.workflow]

#     result = comfyui.run.remote(
#         workflow_file, 
#         endpoint_file,
#         request.config, 
#         client_id
#     )

#     return result
    

# @app.function(image=image)
# @modal.asgi_app()
# def fastapi_app():
#     return web_app
