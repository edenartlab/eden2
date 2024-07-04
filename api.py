"""
- check if user has manna + withdraw
- updating mongo
- if job fails, refund manna
- send back current generators + update
"""

from bson import ObjectId
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from starlette.websockets import WebSocketDisconnect, WebSocketState
import modal

from mongo import MongoBaseModel, agents, tasks, models, users, threads
from agent import Agent, DEFAULT_AGENT_ID
from thread import Thread, UserMessage, get_thread
import s3
# import tools
from tools import get_tools
import auth

from models import Model, Task

tools = get_tools("../workflows")


async def get_or_create_thread(request: dict, user: dict = Depends(auth.authenticate)):
    print("the request", request)
    thread_name = request.get("name")
    if not thread_name:
        raise HTTPException(status_code=400, detail="Thread name is required")
    thread = get_thread(thread_name, create_if_missing=True)
    return {"thread_id": str(thread.id)}



def create(
    request: dict, 
    _: dict = Depends(auth.authenticate_admin)
):
    try:
        task = Task(**request)
        tool = tools[task.workflow]
        task.args = tool.prepare_args(task.args)
        tool.submit(task)
        task.save()  # todo: check for race condition w/ comfy?
        return task
            
    except Exception as e:
        print(e)
        raise HTTPException(status_code=400, detail=str(e))


# async def create(data, user):
#     task = Task(**data, user=user["_id"])
#     if task.workflow == "xhibit":
#         task.workflow = "xhibit/vton"
#     tool = tools.load_tool(task.workflow, f"../workflows/{task.workflow}/api.yaml")
    
#     task.args = tools.prepare_args(tool, task.args)
#     task.save()
    
#     print("ARGS", task.args)
#     result = await tool.execute(task.workflow, task.args)
    
#     if 'error' in result:
#         task.status = "failed"
#         task.error = str(result['error'])
#     else:
#         task.status = "completed"
#         task.result = result
    
#     task.save()
#     yield task.model_dump_json()
    

async def train(args: Dict, user):
    tool = tools.load_tool("lora_trainer", f"tools/lora_trainer/api.yaml")
    task = Task(
        workflow="lora_trainer",
        args=args,
        user=user["_id"]
    )
    task.args = tools.prepare_args(tool, task.args)
    task.save()

    args = task.args.copy()
    args['lora_training_urls'] = "|".join(args['lora_training_urls'])
    print("THE ARGS", args)
    
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



# def create_handler(task_handler):
#     async def websocket_handler(
#         websocket: WebSocket, 
#         user: dict = Depends(auth.authenticate_ws)
#     ):
#         await websocket.accept()
#         try:
#             async for data in websocket.iter_json():
#                 try:
#                     async for response in task_handler(data, user):
#                         await websocket.send_json(response)
#                     break
#                 except Exception as e:
#                     await websocket.send_json({"error": str(e)})
#                     break
#         except WebSocketDisconnect:
#             print("WebSocket disconnected by client")
#         except Exception as e:
#             print(f"Unexpected error: {str(e)}")
#         finally:
#             if websocket.application_state == WebSocketState.CONNECTED:
#                 print("Closing WebSocket...")
#                 await websocket.close()
#     return websocket_handler


web_app = FastAPI()

# web_app.websocket("/ws/create")(create_handler(create))
# web_app.websocket("/ws/chat")(create_handler(chat))
# web_app.websocket("/ws/train")(create_handler(train))

web_app.post("/thread/create")(get_or_create_thread)
web_app.post("/create")(create)


app = modal.App(
    name="tasks2",
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
    container_idle_timeout=30,
)
@modal.asgi_app()
def fastapi_app():
    return web_app


