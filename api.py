import os
import argparse
from bson import ObjectId
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request
from starlette.websockets import WebSocketDisconnect, WebSocketState
import modal

COMFYUI_PROD   = "comfyui"
COMFYUI_STAGE  = "comfyui-dev"
APP_NAME_PROD  = "tools"
APP_NAME_STAGE = "tools-dev"

env = os.getenv("ENV", "STAGE").lower()
if env not in ["prod", "stage"]:
    raise Exception(f"Invalid environment: {env}. Must be PROD or STAGE")
app_name = APP_NAME_PROD if env == "prod" else APP_NAME_STAGE

# os.environ["ENV"] = "STAGE"

# if modal.is_local():
#     parser = argparse.ArgumentParser(description="Serve or deploy Tools API to Modal")
#     subparsers = parser.add_subparsers(dest="method", required=True)
#     parser_serve = subparsers.add_parser("serve", help="Serve Tools API")
#     parser_serve.add_argument("--production", action='store_true', help="Serve production (otherwise staging)")
#     parser_deploy = subparsers.add_parser("deploy", help="Deploy Tools API to Modal")
#     parser_deploy.add_argument("--production", action='store_true', help="Deploy to production (otherwise staging)")
#     args = parser.parse_args()
#     if args.production:
#         app_name = APP_NAME_PROD
#         os.environ["ENVIRONMENT"] = "PROD"
        
import s3
import auth
from mongo import agents, threads
from agent import Agent, DEFAULT_AGENT_ID
from thread import Thread, UserMessage, get_thread
from models import Model, Task
from tool import get_tools
from models import tasks


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


def task_handler(
    request: dict, 
    _: dict = Depends(auth.authenticate_admin)
):
    try:
        task = Task(**request)
        print("new task", task)
        tool = tools[task.workflow]
        handler_id = tool.submit(task) #, app_name=comfyui_app_name)
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
    

async def replicate_create_update(request: Request):
    body = await request.json()
    print("body", body)
    output = body.get("output") 
    handler_id = body.get("id")
    status = body.get("status")

    print("handler_id", handler_id)
    print("status", status)
    print("output", output)
    print("handler_id", handler_id)

    task = tasks.find_one({"handler_id": handler_id})
    # print("task", task)
    if not task:
        raise Exception("Task not found")
    task = Task(**task)

    if status == "failed":
        task.status = "failed"
        print("FAILED", output)
        task.error = output
        task.save()
    
    elif status == "cancelled":
        task.status = "cancelled"
        print("CANCELLED", output)
        task.save()

    elif status == "processing":
        task.status = "running"
        task.save()
    
    elif status == "succeeded":
        output = [
            s3.upload_file_from_url(url, png_to_jpg=True) 
            for url in output
        ]
        task.status = "completed"
        task.result = output
        task.save()

async def replicate_train_update(request: Request):
    body = await request.json()
    output = body.get("output") 
    handler_id = body.get("id")
    status = body.get("status")
    error = body.get("error")

    body.pop("logs")
    print("BODY", body)
    
    task = tasks.find_one({"handler_id": handler_id})
    if not task:
        raise Exception("Task not found")
    task = Task(**task)

    if status == "failed":
        task.status = "failed"
        print("FAILED", output)
        task.error = error
        task.save()

    elif status == "processing":
        task.status = "running"
        task.save()

    elif status == "succeeded":
        if not output:
            raise Exception("No output found")        
        
        output = output[-1]
        
        if "files" in output and "thumbnails" in output:
            checkpoint = s3.upload_file_from_url(output["files"][0])
            thumbnail = s3.upload_file_from_url(output["thumbnails"][0])
            
            if "attributes" in output:
                print(output["attributes"])

            model = Model(
                name=task.args["name"],
                user=task.user,
                args=task.args,
                checkpoint=checkpoint, 
                thumbnail=thumbnail
            )
            model.save()

            task.result = model.id
            task.status = "completed"
        else:        
            task.error = "No files found in output"
            task.status = "failed"

        task.save()


class ChatRequest(BaseModel):
    message: UserMessage
    thread_id: Optional[str] = None
    agent_id: Optional[str] = None

async def chat(data, user):
    print("CHAT REQEUST", data)
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


# def tool_summary(key: str, include_params=True):
#     tool = tools[key]
#     data = {
#         "key": key,
#         "name": tool.name,
#         "description": tool.description,
#         "outputType": tool.output_type
#     } 
#     if include_params:
#         data["tip"] = tool.tip
#         data["parameters"] = [p.model_dump(exclude="comfyui") for p in tool.parameters]
#     return data

    









def tools_list():
    return [tools[t].get_info(include_params=False) for t in tools]

def tools_summary():
    return [tools[t].get_info() for t in tools]


web_app = FastAPI()

web_app.websocket("/ws/chat")(create_handler(chat))
# web_app.websocket("/ws/create")(create_handler(create))
# web_app.websocket("/ws/train")(create_handler(train))
web_app.post("/thread/create")(get_or_create_thread)

web_app.post("/create")(task_handler)
web_app.post("/cancel")(cancel)
web_app.post("/update/create")(replicate_create_update)
web_app.post("/update/train")(replicate_train_update)

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
    .apt_install("git", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1")
    .pip_install("pyjwt", "httpx", "cryptography", "pymongo", "instructor[anthropic]", 
                 "fastapi==0.103.1", "requests", "pyyaml", "python-dotenv", "anthropic",
                 "python-socketio", "replicate", "boto3", "python-magic", "Pillow")
    .copy_local_dir("../workflows", remote_path="/workflows")
    .copy_local_dir("tools", remote_path="/root/tools")
    .env({"ENV": "PROD" if app_name == APP_NAME_PROD else "STAGE"})
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


# if __name__ == "__main__":
#     if args.method == "serve":
#         from modal.cli.run import serve
#         filepath = os.path.abspath(__file__)
#         serve(filepath, timeout=600, env=None)
#     elif args.method == "deploy":
#         from modal.runner import deploy_app
#         deploy_app(app, name=app_name)
