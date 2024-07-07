import os
import argparse
from bson import ObjectId
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from starlette.websockets import WebSocketDisconnect, WebSocketState
import modal

COMFYUI_PROD   = "comfyui"
COMFYUI_STAGE  = "comfyui-dev"
APP_NAME_PROD  = "tools"
APP_NAME_STAGE = "tools-dev"
app_name = APP_NAME_STAGE
os.environ["ENVIRONMENT"] = "STAGE"

if modal.is_local():
    parser = argparse.ArgumentParser(description="Serve or deploy Tools API to Modal")
    subparsers = parser.add_subparsers(dest="method", required=True)
    parser_serve = subparsers.add_parser("serve", help="Serve Tools API")
    parser_serve.add_argument("--production", action='store_true', help="Serve production (otherwise staging)")
    parser_deploy = subparsers.add_parser("deploy", help="Deploy Tools API to Modal")
    parser_deploy.add_argument("--production", action='store_true', help="Deploy to production (otherwise staging)")
    args = parser.parse_args()
    if args.production:
        app_name = APP_NAME_PROD
        os.environ["ENVIRONMENT"] = "PROD"
        
import s3
import auth
from mongo import agents, threads
from agent import Agent, DEFAULT_AGENT_ID
from thread import Thread, UserMessage, get_thread
from models import Model, Task
from tools import get_tools

tools = get_tools("../workflows") | get_tools("tools")


async def get_or_create_thread(
    request: dict, 
    user: dict = Depends(auth.authenticate)
):
    thread_name = request.get("name")
    if not thread_name:
        raise HTTPException(status_code=400, detail="Thread name is required")
    thread = get_thread(thread_name, user, create_if_missing=True)
    return {"thread_id": str(thread.id)}


def create(
    request: dict, 
    _: dict = Depends(auth.authenticate_admin)
):
    try:
        comfyui_app_name = COMFYUI_PROD if app_name == APP_NAME_PROD else COMFYUI_STAGE
        print("THE APP NAME", comfyui_app_name)
        task = Task(**request)
        tool = tools[task.workflow]
        tool.submit(task, app_name=comfyui_app_name)
        task.save() 
        return task
            
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail=str(e))


async def train(args: Dict, user):
    tool = tools.load_tool("tools/lora_trainer")
    task = Task(
        workflow="lora_trainer",
        args=args,
        user=user["_id"]
    )
    task.args = tools.prepare_args(tool, task.args)
    task.save()

    args = task.args.copy()
    args['lora_training_urls'] = "|".join(args['lora_training_urls'])
    print("training args", args)
    
    import replicate
    deployment = replicate.deployments.get("edenartlab/lora-trainer")
    prediction = deployment.predictions.create(args)
    prediction.wait()
    output = prediction.output[-1]
    
    if not output.get('files'):
        task.status = "failed"
        task.error = "No files found in output"
        task.save()
        raise Exception("No files found in output")
    
    tarfile = output['files'][0]
    thumbnail = output['thumbnails'][0]
    
    tarfile_url = s3.upload_file_from_url(tarfile)
    thumbnail_url = s3.upload_file_from_url(thumbnail)
    
    task.result = output
    task.status = "completed"
    task.save()

    model = Model(
        name=args["name"],
        user=user["_id"],
        args=task.args,
        checkpoint=tarfile_url, 
        thumbnail=thumbnail_url
    )

    model.save()
    yield model.model_dump_json()


class ChatRequest(BaseModel):
    message: UserMessage
    thread_id: Optional[str] = None
    agent_id: Optional[str] = None

async def chat(data, user):
    request = ChatRequest(**data)

    agent_id = request.agent_id or DEFAULT_AGENT_ID
    agent = agents.find_one({"_id": ObjectId(agent_id)})
    if not agent:
        raise Exception(f"Agent not found")
    agent = Agent(**agent)

    if request.thread_id:
        thread = threads.find_one({"_id": ObjectId(request.thread_id)})
        if not thread:
            raise Exception("Thread not found")
        thread = Thread(**thread)
    else:
        thread = Thread()

    async for response in thread.prompt(agent, request.message):
        yield {
            "message": response.model_dump_json()
        }


def create_handler(task_handler):
    async def websocket_handler(
        websocket: WebSocket, 
        user: dict = Depends(auth.authenticate_ws)
    ):
        await websocket.accept()
        try:
            async for data in websocket.iter_json():
                try:
                    async for response in task_handler(data, user):
                        await websocket.send_json(response)
                    break
                except Exception as e:
                    await websocket.send_json({"error": str(e)})
                    break
        except WebSocketDisconnect:
            print("WebSocket disconnected by client")
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
        finally:
            if websocket.application_state == WebSocketState.CONNECTED:
                print("Closing WebSocket...")
                await websocket.close()
    return websocket_handler


web_app = FastAPI()

web_app.websocket("/ws/chat")(create_handler(chat))
# web_app.websocket("/ws/create")(create_handler(create))
# web_app.websocket("/ws/train")(create_handler(train))
web_app.post("/thread/create")(get_or_create_thread)
web_app.post("/create")(create)


app = modal.App(
    name=app_name,
    secrets=[
        modal.Secret.from_name("admin-key"),
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("clerk-credentials"),
        modal.Secret.from_name("mongo-credentials"),
        modal.Secret.from_name("openai"),
        modal.Secret.from_name("anthropic"),
        modal.Secret.from_name("replicate"),
    ],
    
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1")
    .pip_install("pyjwt", "httpx", "cryptography", "pymongo", "instructor[anthropic]", 
                 "fastapi==0.103.1", "requests", "pyyaml", "python-dotenv", "anthropic",
                 "python-socketio", "replicate", "boto3", "python-magic", "Pillow")
    .copy_local_dir("../workflows", remote_path="/workflows")
    # .copy_local_dir("tools", remote_path="/root/tools")
)

@app.function(
    image=image, 
    keep_warm=1,
    concurrency_limit=5,
    timeout=1800,
    container_idle_timeout=30
)
@modal.asgi_app()
def fastapi_app():
    return web_app


if __name__ == "__main__":
    if args.method == "serve":
        from modal.cli.run import serve
        filepath = os.path.abspath(__file__)
        serve(filepath, timeout=600, env=None)
    elif args.method == "deploy":
        from modal.runner import deploy_app
        deploy_app(app, name=app_name)
