import os
import jwt
import json
import httpx
import uuid
import modal
import asyncio
from typing import Dict, Any, Optional
from pydantic import BaseModel
from functools import wraps
import fastapi
from fastapi import FastAPI, WebSocket, status, Request, Response, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.websockets import WebSocketDisconnect
from pydantic import BaseModel


from mongo import connect

"""
- proper auth error handling
- config error handling
- check manna
- if job fails, refund manna

"""



snapshots = ["txt2img", "txt2vid_lcm", "steerable_motion", "img2vid"]

web_app = FastAPI()


class WorkflowRequest(BaseModel):
    workflow: str
    config: Dict[str, Any]
    client_id: Optional[str] = None


def get_auth_credentials(headers: dict):
    token = headers.get("Authorization")
    api_key = headers.get("X-Api-Key")
    
    db = mongo.connect()
    print(db)

    if token:
        print("get token")
        token = token.split(" ")[1]  # Extract the token part from "Bearer <token>"
        print("THE TOKEN IS:")

        print(token)
        # print(JWTBearer.CLERK_PEM_PUBLIC_KEY)
        try:
            CLERK_PEM_PUBLIC_KEY = os.environ.get("CLERK_PEM_PUBLIC_KEY")
            decoded_token = jwt.decode(token, CLERK_PEM_PUBLIC_KEY, algorithms=["RS256"])
            user_id = decoded_token.get("sub")
            print("THE USER ID")
            db = mongo.connect()
            user = db["users"].find_one({"userId": user_id})
            print(user)
            #user = get_user(userId)
            print("OK!!!")
            if user:
                return user
            else:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired Token")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Token")
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    
    elif api_key:
        db = mongo.connect()
        api_key = db["apikeys"].find_one({"apiKey": api_key})
        if api_key:
            user = db["users"].find_one({"_id": ObjectId(api_key["user"])})
            return user
        else:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authentication")

def auth_user_post(request: Request):
    return get_auth_credentials(request.headers)

async def auth_user_websocket(websocket: WebSocket):
    return get_auth_credentials(websocket.headers)


@web_app.post("/tasks/create")
def create(
    request: WorkflowRequest,
    user: dict = Depends(auth_user_post)
):
    if request.workflow not in snapshots:
        raise HTTPException(status_code=400, detail="Invalid workflow")

    if request.client_id is None:
        client_id = str(uuid.uuid4())

    comfyui = f"ComfyUIServer_{request.workflow}"
    cls = modal.Cls.lookup("eden-comfyui", comfyui)

    task = cls().run.spawn(
        request.workflow, 
        request.config, 
        client_id
    )
    
    return {"task_id": task.object_id}


@web_app.post("/tasks/run")
def run(
    request: WorkflowRequest,
    user: dict = Depends(auth_user_post)
):
    if request.workflow not in snapshots:
        raise HTTPException(status_code=400, detail="Invalid workflow")

    if request.client_id is None:
        client_id = str(uuid.uuid4())

    comfyui = f"ComfyUIServer_{request.workflow}"
    cls = modal.Cls.lookup("eden-comfyui", comfyui)

    result = cls().run.remote(
        request.workflow, 
        request.config, 
        client_id
    )

    return result


@web_app.websocket("/ws/tasks/run")
async def websocket_endpoint(
    websocket: WebSocket, 
    user: str = Depends(auth_user_websocket)
):
    print("THE IUSER IOS !!!" )
    print(user)

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="There IS NO USER")

    await websocket.accept()
    while True:
        try:
            request_json = await websocket.receive_json()
            #request = WorkflowRequest(**request_json)
            #result = run(request, user)
            result = {"status": "running"}
            await websocket.send_json(json.dumps(result))
        except WebSocketDisconnect:
            print("WebSocket connection closed by the client.")
            break
        except Exception as e:
            print(f"WebSocket error: {e}")
            break


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
    import mongo
    from bson.objectid import ObjectId

@app.function(image=image)
@modal.asgi_app()
def fastapi_app():
    return web_app



"""
X check token security
    - abstract token
    - clerk auth
- check if user has manna + withdraw
- updating mongo
- task_id + polling + SSE + client library 
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