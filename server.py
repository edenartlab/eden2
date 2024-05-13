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

from auth import authenticate, authenticate_ws

snapshots = ["txt2img", "txt2vid_lcm", "steerable_motion", "img2vid"]

web_app = FastAPI()

class WorkflowRequest(BaseModel):
    workflow: str
    config: Dict[str, Any]
    client_id: Optional[str] = None


@web_app.post("/tasks/create")
async def create(
    request: WorkflowRequest,
    user: dict = Depends(authenticate)
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
    user: dict = Depends(authenticate)
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


@web_app.websocket("/ws/tasks/run")
async def websocket_endpoint(websocket: WebSocket, user: dict = Depends(authenticate_ws)):
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
        modal.Secret.from_name("server-credentials"),
        modal.Secret.from_name("clerk-credentials"),
        modal.Secret.from_name("mongo-credentials"),
    ],
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1")
    .pip_install("pyjwt", "httpx", "cryptography", "pymongo")
)

with image.imports():
    import os
    import mongo
    from bson.objectid import ObjectId
    CLERK_PEM_PUBLIC_KEY = os.getenv("CLERK_PEM_PUBLIC_KEY")


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

"""



"""
curl -X POST -H "Content-Type: application/json" -H \
    "Authorization: Bearer eyJhbGciOiJSUzI1NiIsImNhdCI6ImNsX0I3ZDRQRDExMUFBQSIsImtpZCI6Imluc18yVXluSWYzVXVRNDdBNEdyZm1ITFdjME1rOWUiLCJ0eXAiOiJKV1QifQ.eyJhenAiOiJodHRwczovL2FwcC5lZGVuLmFydCIsImV4cCI6MTcxNTQ2Njg0MSwiaWF0IjoxNzE1NDY2NzgxLCJpc3MiOiJodHRwczovL2NsZXJrLmVkZW4uYXJ0IiwibmJmIjoxNzE1NDY2NzcxLCJzaWQiOiJzZXNzXzJnS1RzQUVxbkx5SFJ1R2ptNDZDM1RYR21uVyIsInN1YiI6InVzZXJfMldkOUplY1BEcXJ5WTJPVFhaM0FCV1BWZEFlIn0.d8oOCCsdzqWcKtQAtS_W2bZSAb5FqGcMtbJZaaI3U65gZUwxcm9EaRGBVULsokH0teLmoHKtYM34GoD1ljCelXfqZ-83UIwT5gBvNywPLu3sGBMdFW0MJ8Ayl_sxvNrxlHqTHKsiFaDRJgx8x4Rdt_QKUe-DxzJUihBOf30bKZuzNWVy-NANSq3NUxVztW1moGkA0R0NJrpAsFWv6_zlCvurZvm2yJLJ5p763tVMLwKe2jsZkkyP-VeDDN0kxg7kz7Njq9XYTeiafKyb-vIljGtpn1QAHttRvjz2APeQ8_fq1vfpu9SjsR2D0Lczp227ie6uTGMf5rs-hhDKmtBtHQ" \
    https://edenartlab--eden-server-fastapi-app-dev.modal.run/protected-endpoint
    http://127.0.0.1:8000/protected-endpoint

"""

"""

time curl -X POST \
  "https://edenartlab--eden-server-fastapi-app-dev.modal.run/tasks/create" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIsImNhdCI6ImNsX0I3ZDRQRDExMUFBQSIsImtpZCI6Imluc18yVXluSWYzVXVRNDdBNEdyZm1ITFdjME1rOWUiLCJ0eXAiOiJKV1QifQ.eyJhenAiOiJodHRwczovL2FwcC5lZGVuLmFydCIsImV4cCI6MTcxNTQ2NzE5MSwiaWF0IjoxNzE1NDY3MTMxLCJpc3MiOiJodHRwczovL2NsZXJrLmVkZW4uYXJ0IiwibmJmIjoxNzE1NDY3MTIxLCJzaWQiOiJzZXNzXzJnS1RzQUVxbkx5SFJ1R2ptNDZDM1RYR21uVyIsInN1YiI6InVzZXJfMldkOUplY1BEcXJ5WTJPVFhaM0FCV1BWZEFlIn0.Ks8oI2jtgXf7dTcSk7USQeZ81eyf0n5ERiV3LmnJJTMtT7Z92_MWkcGHCXmPqPoBu9JLDEuhxyXO5uvHCd3QX0XQJmfiR3jgy0NVuU5J7Hclad2qQKymiGdrwzqbZCHIHTvidAlTauPPr7XC13QlYuQwswZCnDksl0IgGnnOuuv06KzCCdaXPiCDS3bnfFl9T-2Fj6wIc5UiAIRERNNwS11Hh1swc9nY0s3cAIJ9zQp6n_CRP_xjvZx7uRIPexoSLNSEAI26eYibiRWJgdIFMK5heqvJQA6daqX51ec6aako2ahIc5jTjHggSyXIhEP7CQXnfwcusdiJW1OH3Sv2Vg" \
  -d '{
    "workflow":"txt2img",
    "config": {
      "prompt":"A cat and a dog eating a pizza",
      "negative_prompt":"lowres, bad anatomy, bad hands, text, jpg artifacts",
      "width":768,
      "height":768
    }
  }'


time curl -X POST \
  "https://edenartlab--eden-server-fastapi-app-dev.modal.run/tasks/run" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: thepassword" \
  -d '{
    "workflow":"txt2img",
    "config": {
      "prompt":"A cat and a dog eating a pizza",
      "negative_prompt":"lowres, bad anatomy, bad hands, text, jpg artifacts",
      "width":768,
      "height":768
    }
  }'


time curl -X GET \
  "https://edenartlab--eden-server-fastapi-app-dev.modal.run/result/fc-01HXMP1JR6SE6A6Z12KD40HC0D" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" 

"""




"""
x proper auth error handling
- config error handling
- check manna
- if job fails, refund manna

"""
