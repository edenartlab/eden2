import os
import modal
from bson import ObjectId
from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request
from starlette.websockets import WebSocketDisconnect, WebSocketState

COMFYUI_PROD   = "comfyui-dev"
COMFYUI_STAGE  = "comfyui-dev"
APP_NAME_PROD  = "tools"
APP_NAME_STAGE = "tools-dev"

env = os.getenv("ENV", "STAGE").lower()
if env not in ["prod", "stage"]:
    raise Exception(f"Invalid environment: {env}. Must be PROD or STAGE")
app_name = APP_NAME_PROD if env == "prod" else APP_NAME_STAGE
        
import auth
from mongo import agents, threads
from agent import Agent
from thread2 import Thread, UserMessage, prompt
from models import Task
from tool2 import get_tools, get_comfyui_tools, replicate_update_task
from models import tasks

api_tools = [
    "txt2img", "flux", "SD3", "img2img", "controlnet", "remix", "inpaint", "outpaint", "background_removal", "clarity_upscaler", "face_styler", 
    "animate_3D", "txt2vid", "txt2vid_lora", "img2vid", "vid2vid_sdxl", "style_mixing", "video_upscaler", 
    "stable_audio", "audiocraft", "reel",
    "xhibit/vton", "xhibit/remix", "beeple_ai",
    "moodmix", "lora_trainer",
]

tools = get_comfyui_tools("../workflows/environments") | get_comfyui_tools("../private_workflows/environments") | get_tools("tools")
tools = {k: v for k, v in tools.items() if k in api_tools}


async def get_or_create_thread(
    request: dict, 
    user: dict = Depends(auth.authenticate)
):
    thread_name = request.get("name")
    if not thread_name:
        raise HTTPException(status_code=400, detail="Thread name is required")
    thread = Thread.from_name(thread_name, user, create_if_missing=True)
    return {"thread_id": str(thread.id)}


def task_handler(
    request: dict, 
    _: dict = Depends(auth.authenticate_admin)
):
    try:
        task = Task(**request)
        tool = tools[task.workflow]
        tool.submit(task)
        task.reload()
        return task
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail=str(e))


def cancel(
    request: dict, 
    _: dict = Depends(auth.authenticate_admin)
):
    try:
        task_id = request.get("taskId")
        print("receive cancel request", task_id)
        task = Task.from_id(task_id)
        
    except Exception as e:
        print("error canceling task", e)
        print(e)
        raise HTTPException(status_code=400, detail=str(e))

    if task.status in ["completed", "failed", "cancelled"]:
        return {"status": task.status}
    
    tool = tools[task.workflow]
    try:
        print("cancel task", task.workflow)
        tool.cancel(task)
        return {"status": task.status}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))
    

async def replicate_update(request: Request):
    body = await request.json()
    body.pop("logs")
    print("body", body)
    output = body.get("output") 
    handler_id = body.get("id")
    status = body.get("status")
    error = body.get("error")

    task = tasks.find_one({"handler_id": handler_id})
    if not task:
        raise Exception("Task not found")
    
    task = Task(**task)
    tool = tools[task.workflow]
    output_handler = tool.output_handler

    _ = replicate_update_task(
        task,
        status, 
        error, 
        output, 
        output_handler
    )


class ChatRequest(BaseModel):
    message: UserMessage
    thread_id: Optional[str] = None
    agent_id: str = "6678c3495ecc0b3ed1f4fd8f"

async def chat(data, user):
    request = ChatRequest(**data)
    agent = agents.find_one({"_id": ObjectId(request.agent_id)})
    if not agent:
        raise Exception(f"Agent not found")
    agent = Agent(**agent)

    # todo: check if user owns this agent

    if request.thread_id:
        thread = threads.find_one({"_id": ObjectId(request.thread_id)})
        if not thread:
            raise Exception("Thread not found")
        thread = Thread(**thread)
    else:
        thread = Thread()

    async for response in prompt(thread, agent, request.message):
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


def tools_list():
    return [tools[t].get_info(include_params=False) for t in api_tools]

def tools_summary():
    return [tools[t].get_info() for t in api_tools]


web_app = FastAPI()

web_app.websocket("/ws/chat")(create_handler(chat))
web_app.post("/thread/create")(get_or_create_thread)

web_app.post("/create")(task_handler)
web_app.post("/cancel")(cancel)
web_app.post("/update")(replicate_update)

web_app.get("/tools")(tools_summary)
web_app.get("/tools/list")(tools_list)
for t in tools:
    web_app.get(f"/tool/{t}")(lambda key=t: tools[key].get_info())


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
    .apt_install("git", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1", "ffmpeg")
    .pip_install("pyjwt", "httpx", "cryptography", "pymongo", "instructor[anthropic]", "anthropic",
                 "fastapi==0.103.1", "requests", "pyyaml", "python-dotenv", "moviepy",
                 "python-socketio", "replicate", "boto3", "python-magic", "Pillow", "pydub")
    #.copy_local_dir("../workflows/public_workflows", remote_path="/workflows/public_workflows")
    #.copy_local_dir("../workflows/private_workflows", remote_path="/workflows/private_workflows")
    .copy_local_dir("../workflows", remote_path="/workflows")
    .copy_local_dir("../private_workflows", remote_path="/private_workflows")
    .copy_local_dir("tools", remote_path="/root/tools")
    .env({"ENV": "PROD" if app_name == APP_NAME_PROD else "STAGE"})
    .env({"MODAL_SERVE": "1" if os.getenv("MODAL_SERVE") else "0"})
)

@app.function(
    image=image, 
    keep_warm=1,
    concurrency_limit=10,
    container_idle_timeout=60,
    timeout=60
)
@modal.asgi_app()
def fastapi_app():
    return web_app
