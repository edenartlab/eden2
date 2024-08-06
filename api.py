import os
import modal
from bson import ObjectId
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request
from starlette.websockets import WebSocketDisconnect, WebSocketState

COMFYUI_PROD   = "comfyui"
COMFYUI_STAGE  = "comfyui-dev"
APP_NAME_PROD  = "tools"
APP_NAME_STAGE = "tools-dev"

env = os.getenv("ENV", "STAGE").lower()
if env not in ["prod", "stage"]:
    raise Exception(f"Invalid environment: {env}. Must be PROD or STAGE")
app_name = APP_NAME_PROD if env == "prod" else APP_NAME_STAGE
        
import s3
import auth
import utils
from mongo import agents, threads
from agent import Agent, DEFAULT_AGENT_ID
from thread2 import Thread, UserMessage, prompt
from models import Model, Task
from tool import get_tools
from models import tasks


tools = get_tools("../workflows/public_workflows") | get_tools("tools") | get_tools("../workflows/private_workflows")
print("Tools", tools)


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
        print("new task", task)
        tool = tools[task.workflow]
        handler_id = tool.submit(task)
        task.handler_id = handler_id
        task.save()
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
        task = Task.from_id(task_id)
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
    

def replicate_process_normal(output, task):
    try:
        if not output:
            raise Exception("No output found")
        
        results = []
        for url in output:
            media_attributes, thumbnail = utils.get_media_attributes(url)
            url = s3.upload_file_from_url(url, png_to_jpg=True)
            thumbnail = utils.PIL_to_bytes(thumbnail)
            thumbnail_url = s3.upload_buffer(thumbnail, webp=True)
            results.append({
                "url": url,
                "thumbnail": thumbnail_url,
                "metadata": None,
                "mediaAttributes": media_attributes
            })

        task.status = "completed"
        task.result = results
    
    except Exception as e:
        print("Error uploading output", e)
        task.status = "failed"
        task.error = str(e)


def replicate_process_eden(output, task, save_model=False):
    try:
        output = output[-1]
        if not output or "files" not in output:
            raise Exception("No output found")         

        file_url = s3.upload_file_from_url(output["files"][0])
        metadata = output.get("attributes")

        if save_model:
            media_attributes = {"type": "application/x-tar"}
            thumbnail_url = s3.upload_file_from_url(output["thumbnails"][0], webp=True)
        
            model = Model(
                name=task.args["name"],
                user=task.user,
                args=task.args,
                task=task.id,
                checkpoint=file_url, 
                thumbnail=thumbnail_url
            )
            model.save()
        
            task.result = [{
                "url": file_url,
                "thumbnail": thumbnail_url,
                "metadata": metadata,
                "mediaAttributes": media_attributes,
                "model": model.id
            }]
            
        else:
            media_attributes, thumbnail = utils.get_media_attributes(file_url)
            thumbnail_url = s3.upload_buffer(utils.PIL_to_bytes(thumbnail), webp=True) if thumbnail else None

            task.result = [{
                "url": file_url,
                "thumbnail": thumbnail_url,
                "metadata": metadata,
                "mediaAttributes": media_attributes
            }]

        task.status = "completed"
    
    except Exception as e:
        task.status = "failed"
        task.error = str(e)


async def replicate_update(request: Request):
    body = await request.json()
    body.pop("logs")
    output = body.get("output") 
    handler_id = body.get("id")
    status = body.get("status")
    error = body.get("error")

    print("handler_id", handler_id)
    print("status", status)
    print("output", output)
    print("handler_id", handler_id)

    task = tasks.find_one({"handler_id": handler_id})
    if not task:
        raise Exception("Task not found")
    
    task = Task(**task)

    if status == "failed":
        task.status = "failed"
        task.error = error
        task.save()
    
    elif status == "cancelled":
        task.status = "cancelled"
        task.save()

    elif status == "processing":
        task.status = "running"
        task.save()
    
    elif status == "succeeded":
        tool = tools[task.workflow]        
        if tool.output_handler == "eden":
            replicate_process_eden(output, task)
        elif tool.output_handler == "trainer":
            replicate_process_eden(output, task, save_model=True)
        else:
            replicate_process_normal(output, task)
        
        task.save()


class ChatRequest(BaseModel):
    message: UserMessage
    thread_id: Optional[str] = None
    agent_id: Optional[str] = None

async def chat(data, user):
    print("chat request", data)
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
    return [tools[t].get_info(include_params=False) for t in tools]

def tools_summary():
    return [tools[t].get_info() for t in tools]


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
    .copy_local_dir("../workflows/public_workflows", remote_path="/workflows/public_workflows")
    .copy_local_dir("../workflows/private_workflows", remote_path="/workflows/private_workflows")
    .copy_local_dir("tools", remote_path="/root/tools")
    .env({"ENV": "PROD" if app_name == APP_NAME_PROD else "STAGE"})
    .env({"MODAL_SERVE": "1" if os.getenv("MODAL_SERVE") else "0"})
)


@app.function(
    image=image, 
    keep_warm=1,
    # concurrency_limit=5,
    timeout=1800,
    container_idle_timeout=30
)
@modal.asgi_app()
def fastapi_app():
    return web_app
