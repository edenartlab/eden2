import os
import modal
from bson import ObjectId
from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request
from starlette.websockets import WebSocketDisconnect, WebSocketState

from mongo import get_collection

env = os.getenv("ENV", "STAGE")
if env not in ["PROD", "STAGE"]:
    raise Exception(f"Invalid environment: {env}. Must be PROD or STAGE")
app_name = "tools" if env == "PROD" else "tools-dev"
        
import auth
from agent import Agent
from thread import Thread, UserMessage, async_prompt
from models import Task
from tool import get_tools, get_comfyui_tools, replicate_update_task

api_tools = [
    "txt2img", "flux-schnell", "flux-dev", "SD3", "img2img", "controlnet", "layer_diffusion", "remix", "inpaint", "outpaint", "background_removal", "background_removal_video", "storydiffusion", "face_styler", "upscaler",
    "animate_3D", "txt2vid",  "img2vid", "vid2vid_sdxl", "style_mixing", "video_upscaler", 
    "stable_audio", "audiocraft", "reel",
    "xhibit_vton", "xhibit_remix", "beeple_ai",
    "moodmix", "lora_trainer",
    "news",
]

agents = get_collection("agents", env=env)
threads = get_collection("threads", env=env)

tools = get_comfyui_tools("../workflows/workspaces") | get_comfyui_tools("../private_workflows/workspaces") | get_tools("tools")
if env == "PROD":
    tools = {k: v for k, v in tools.items() if k in api_tools}


async def get_or_create_thread(
    request: dict, 
    user: dict = Depends(auth.authenticate)
):
    thread_name = request.get("name")
    if not thread_name:
        raise HTTPException(status_code=400, detail="Thread name is required")
    thread = Thread.from_name(thread_name, user_id=user["_id"], env=env, create_if_missing=True)
    return {"thread_id": str(thread.id)}


def task_handler(
    request: dict, 
    _: dict = Depends(auth.authenticate_admin)
):
    try:
        print("task request", request)
        workflow = request.get("workflow")
        if workflow not in tools:
            raise HTTPException(status_code=400, detail=f"Invalid workflow: {workflow}")
        tool = tools[workflow]
        task = Task(env=env, output_type=tool.output_type, **request)
        print("task 1", task)
        tool.submit(task)
        task.reload()
        print("task 2", task)
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
        task = Task.from_id(task_id, env=env)        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if task.status in ["completed", "failed", "cancelled"]:
        return {"status": task.status}
    
    tool = tools[task.workflow]
    try:
        tool.cancel(task)
        return {"status": task.status}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))
    

async def replicate_update(request: Request):
    print("receive replicate update request")
    body = await request.json()
    body.pop("logs")
    print("body", body)
    output = body.get("output") 
    handler_id = body.get("id")
    status = body.get("status")
    error = body.get("error")

    task = Task.from_handler_id(handler_id, env=env)
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
    
    agent = Agent.from_id(request.agent_id, env=env)
    # todo: check if user owns this agent

    if request.thread_id:
        thread = threads.find_one({"_id": ObjectId(request.thread_id)})
        if not thread:
            raise Exception("Thread not found")
        thread = Thread.from_id(request.thread_id, env=env)
    else:
        thread = Thread(env=env)

    async for response in async_prompt(thread, agent, request.message):
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
    return [tools[t].get_info(include_params=False) for t in api_tools if t in tools]

def tools_summary():
    return [tools[t].get_info() for t in api_tools if t in tools]


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
        modal.Secret.from_name("clerk-credentials"),
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("mongo-credentials"),
        modal.Secret.from_name("openai"),
        modal.Secret.from_name("anthropic"),
        modal.Secret.from_name("replicate"),
        modal.Secret.from_name("sentry"),
    ],   
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .env({"ENV": env, "MODAL_SERVE": os.getenv("MODAL_SERVE")})
    .apt_install("git", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1", "ffmpeg")
    .pip_install("pyjwt", "httpx", "cryptography", "pymongo", "instructor[anthropic]", "anthropic",
                 "fastapi==0.103.1", "requests", "pyyaml", "python-dotenv", "moviepy",
                 "python-socketio", "replicate", "boto3", "python-magic", "Pillow", "pydub", "sentry_sdk")
    .copy_local_dir("../workflows", remote_path="/workflows")
    .copy_local_dir("../private_workflows", remote_path="/private_workflows")
    .copy_local_dir("tools", remote_path="/root/tools")
)

@app.function(
    image=image, 
    keep_warm=1,
    concurrency_limit=10,
    container_idle_timeout=60,
    timeout=3600
)
@modal.asgi_app()
def fastapi_app():
    return web_app
