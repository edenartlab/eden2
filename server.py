import os
import json
import uuid
import modal
import asyncio
import fastapi
from fastapi import FastAPI, WebSocket, status, Request, Response, HTTPException, Depends
from typing import Dict, Any, Optional
from pydantic import BaseModel
from functools import wraps
from starlette.websockets import WebSocketDisconnect, WebSocketState
from pydantic import BaseModel

import auth
import agent
from agent import UserMessage, Session



snapshots = ["txt2img", "txt2vid_lcm", "steerable_motion", "img2vid"]

web_app = FastAPI()

class WorkflowRequest(BaseModel):
    workflow: str
    config: Dict[str, Any]
    client_id: Optional[str] = None


@web_app.post("/tasks/create")
async def create(
    request: WorkflowRequest,
    user: dict = Depends(auth.authenticate)
):
    if request.workflow not in snapshots:
        raise HTTPException(status_code=400, detail="Invalid workflow")

    if request.client_id is None:
        client_id = str(uuid.uuid4())

    comfyui = f"ComfyUIServer_{request.workflow}"
    cls = modal.Cls.lookup("eden-comfyui", comfyui)

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

    if request.client_id is None:
        client_id = str(uuid.uuid4())

    comfyui = f"ComfyUIServer_{request.workflow}"
    cls = modal.Cls.lookup("eden-comfyui", comfyui)

    workflow_file = f"workflows/{request.workflow}.json"
    endpoint_file = f"endpoints/{request.workflow}.yaml"

    result = cls().run.remote(
        workflow_file,
        endpoint_file,
        request.config, 
        client_id
    )

    return result



class ChatRequest(BaseModel):
    session_id: str
    message: UserMessage



from modal import Dict

sessions = Dict.from_name("Sessions", create_if_missing=True)



@web_app.post("/tasks/chat")
async def run2(
    request: ChatRequest,
    # session_id: str = Body(...),
    user: dict = Depends(auth.authenticate)
):

    # if request.workflow not in snapshots:
    #     raise HTTPException(status_code=400, detail="Invalid workflow")

    # if request.client_id is None:
    #     client_id = str(uuid.uuid4())

    # comfyui = f"ComfyUIServer_{request.workflow}"
    # cls = modal.Cls.lookup("eden-comfyui", comfyui)

    # workflow_file = f"workflows/{request.workflow}.json"
    # endpoint_file = f"endpoints/{request.workflow}.yaml"

    # result = cls().run.remote(
    #     workflow_file,
    #     endpoint_file,
    #     request.config, 
    #     client_id
    # )

    # UserMessage(
    #     content="can you animate this?",
    #     settings={"style": "starry night style"},
    #     attachments=["https://edenartlab-lfs.s3.amazonaws.com/comfyui/models2/checkpoints/photonLCM_v10.safetensors"]
    # )

    if not request.session_id in sessions:
        sessions[request.session_id] = Session("You are an assistant. Pay attention to the settings in your response.")

    session = sessions[request.session_id]


    #session = Session("You are an assistant. Pay attention to the settings in your response.")
    print("session_id", request.session_id)
    response = session.prompt(request.message)


    # print("session_id", request.session_id)
    # response = agent.chat(
    #     session_id="session_id",
    #     message=request.message
    # )

    return response


@web_app.websocket("/ws/tasks/run")
async def websocket_endpoint(websocket: WebSocket, user: dict = Depends(auth.authenticate_ws)):
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
        return fastapi.responses.JSONResponse(content="", status_code=202)
    return result


app = modal.App(
    name="eden-server",
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
    .pip_install("pyjwt", "httpx", "cryptography", "pymongo", "instructor==1.2.6", "fastapi==0.103.1", "pyyaml") #, "tqdm")
    .copy_local_dir("endpoints", remote_path="/root/endpoints")
    # .copy_local_file("agent2.py", remote_path="/root/agent2.py")
)

with image.imports():
    import os
    import mongo
    from bson.objectid import ObjectId
    
    


@app.function(image=image)
@modal.asgi_app()
def fastapi_app():
    return web_app



"""
X check token security
    x abstract token
    x clerk auth
- task_id + polling + SSE + client library 
- sdk library


- check if user has manna + withdraw
- updating mongo
- send back current generators + update

x proper auth error handling
- config error handling
- check manna
- if job fails, refund manna

"""
