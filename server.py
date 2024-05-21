import json
import modal
import os
from bson.objectid import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.requests import Request
import json
from bson import ObjectId
from fastapi import FastAPI, WebSocket, status, Request, Response, HTTPException, Depends
from typing import Dict, Any, Optional
from pydantic import BaseModel
from functools import wraps
from starlette.websockets import WebSocketDisconnect, WebSocketState
from thread import Thread, UserMessage, AssistantMessage
from pydantic import BaseModel
from pydantic.json_schema import SkipJsonSchema

import auth
#import agent
#from agent import UserMessage, Session
from thread import UserMessage, Thread, default_system_message
from mongo import MongoBaseModel, threads


snapshots = [
    "txt2img", 
    "txt2vid_lcm", 
    "img2vid", 
    "vid2vid", 
    "style_mixing"
]

web_app = FastAPI()

class WorkflowRequest(BaseModel):
    workflow: str
    config: Dict[str, Any]

class ChatRequest(BaseModel):
    message: UserMessage
    thread_id: Optional[str] = None


@web_app.post("/tasks/create")
async def create(
    request: WorkflowRequest,
    user: dict = Depends(auth.authenticate)
):
    if request.workflow not in snapshots:
        raise HTTPException(status_code=400, detail="Invalid workflow")

    client_id = user["username"]

    comfyui = f"ComfyUIServer_{request.workflow}"
    cls = modal.Cls.lookup("comfyui", comfyui)

    workflow_file = f"workflows/{request.workflow}.json"
    endpoint_file = f"endpoints/{request.workflow}.yaml"
    
    task = cls().run.spawn(
        workflow_file,
        endpoint_file,
        request.config, 
        client_id
    )
    
    return {"task_id": task.object_id}


@web_app.post("/tasks/run")
async def run(
    request: WorkflowRequest,
    user: dict = Depends(auth.authenticate)
):
    if request.workflow not in snapshots:
        raise HTTPException(status_code=400, detail="Invalid workflow")

    client_id = user["username"]

    comfyui = f"ComfyUIServer_{request.workflow}"
    cls = modal.Cls.lookup("comfyui", comfyui)

    workflow_file = f"workflows/{request.workflow}.json"
    endpoint_file = f"endpoints/{request.workflow}.yaml"

    result = cls().run.remote(
        workflow_file,
        endpoint_file,
        request.config, 
        client_id
    )

    return result



@web_app.post("/tasks/chat")
async def run3(
    request: ChatRequest,
    user: dict = Depends(auth.authenticate)
):
    if request.thread_id is not None:
        thread = threads.find_one({"_id": ObjectId(request.thread_id)})
        if thread is None:
            raise HTTPException(status_code=400, detail="Thread ID not found")

        thread = Thread(**thread)
    else:
        system_message = "You are an assistant that knows how to use Eden. ..."
        thread = Thread(system_message=system_message)

    async def event_stream():
        async for response in thread.prompt(request.message):#, system_message=system_message):
            Thread.save(thread, threads)
            result = json.dumps({
                "thread_id": str(thread.id),
                "message": response.model_dump_json()
            }) + "\n"
            yield result

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@web_app.websocket("/ws/tasks/run")
async def websocket_endpoint(
    websocket: WebSocket, 
    user: dict = Depends(auth.authenticate_ws)
):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            request = WorkflowRequest(**data)
            result = await run(request, user)
            await websocket.send_json(json.dumps(result))
    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if websocket.application_state == WebSocketState.CONNECTED:
            await websocket.close()


@web_app.get("/task/{task_id}")
async def poll(task_id: str):
    from modal.functions import FunctionCall
    function_call = FunctionCall.from_id(task_id)
    try:
        result = function_call.get(timeout=0)
    except TimeoutError:
        return JSONResponse(content="", status_code=202)
    return result








app = modal.App(
    name="tasks",
    secrets=[
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("clerk-credentials"),
        modal.Secret.from_name("mongo-credentials"),
        modal.Secret.from_name("openai"),
    ],
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1")
    .pip_install("pyjwt", "httpx", "cryptography", "pymongo", "instructor==1.2.6", "fastapi==0.103.1", "pyyaml", "python-dotenv") #, "tqdm")
    .copy_local_dir("endpoints", remote_path="/root/endpoints")
    # .copy_local_file("agent2.py", remote_path="/root/agent2.py")
)


    
@app.function(image=image)
@modal.asgi_app()
def fastapi_app():
    return web_app



"""
X check token security
    x abstract token
    x clerk auth
- task_id + polling + SSE + client library 
x sdk library


- check if user has manna + withdraw
- updating mongo
- send back current generators + update

x proper auth error handling
- config error handling
- check manna
- if job fails, refund manna

"""
