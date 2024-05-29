import modal
from typing import Optional
from bson.objectid import ObjectId
from fastapi import FastAPI, HTTPException
from starlette.websockets import WebSocketState
from bson import ObjectId
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, Any, Optional
from pydantic import BaseModel
from functools import wraps
from starlette.websockets import WebSocketDisconnect, WebSocketState
from thread import Thread, UserMessage, AssistantMessage
from pydantic import BaseModel
from pydantic.json_schema import SkipJsonSchema

import auth
from mongo import threads
from thread import Thread, UserMessage
from endpoint import tools, endpoint_summary


snapshots = [
    "txt2img", 
    "txt2vid_lcm", 
    "img2vid", 
    "vid2vid", 
    "style_mixing"
]

web_app = FastAPI()


default_system_message = (
    "You are an assistant that knows how to use Eden. "
    "You have the following tools available to you: "
    "\n\n---\n{endpoint_summary}\n---"
    "\n\nIf the user clearly wants you to make something, select exactly ONE of the tools. Do NOT select multiple tools. Do NOT hallucinate any tool, especially do not use 'multi_tool_use' or 'multi_tool_use.parallel.parallel'. Only tools allowed: {tool_names}." 
    "If the user is just making chat with you or asking a question, leave the tool null and just respond through the chat message. "
    "If you're not sure of the user's intent, you can select no tool and ask the user for clarification or confirmation. " 
    "Look through the whole conversation history for clues as to what the user wants. If they are referencing previous outputs, make sure to use them."
)


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
        finally:
            if websocket.application_state == WebSocketState.CONNECTED:
                print("Closing...")
                await websocket.close()
    return websocket_handler


class ChatRequest(BaseModel):
    message: UserMessage
    thread_id: Optional[str] = None

async def chat(data, user):
    request = ChatRequest(**data)
    print(request)

    if request.thread_id:
        thread = threads.find_one({"_id": ObjectId(request.thread_id)})
        if not thread:                        # await websocket.send_json({"error": "Thread ID not found"})
            raise Exception("Thread ID not found")
        thread = Thread(**thread)
    else:
        thread = Thread(system_message=default_system_message)

    async for response in thread.prompt(request.message):
        yield {
            "thread_id": str(thread.id),
            "message": response.model_dump_json()
        }


class CreateRequest(BaseModel):
    endpoint: str
    config: Dict[str, Any]

async def create(data, user):
    request = CreateRequest(**data)
    print(request)
    
    if request.endpoint not in snapshots:
        raise HTTPException(status_code=400, detail="Invalid workflow")

    cls = modal.Cls.lookup("dev-comfyui", request.endpoint)

    workflow_file = f"workflows/{request.endpoint}.json"
    endpoint_file = f"endpoints/{request.endpoint}.yaml"
    result = cls().run.remote(workflow_file, endpoint_file, request.config, "client_id")

    yield {
        "task_id": "taskid",
        "result": result,
    }


web_app.websocket("/ws/create")(create_handler(create))
web_app.websocket("/ws/chat")(create_handler(chat))




import modal

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
    .pip_install("pyjwt", "httpx", "cryptography", "pymongo", "instructor==1.2.6", "fastapi==0.103.1", "pyyaml", "python-dotenv", "python-socketio") #, "tqdm")
    .copy_local_dir("endpoints", remote_path="/root/endpoints")
    # .copy_local_file("agent2.py", remote_path="/root/agent2.py")
)
    
@app.function(
    image=image, 
    keep_warm=1,
    concurrency_limit=10
)
@modal.asgi_app()
def fastapi_app():
    return web_app







################################################################################
################################################################################
################################################################################
## SOCKET IO

# import asyncio
# from fastapi import FastAPI, WebSocket
# import socketio
# import uvicorn

# # Create a FastAPI app and a Socket.IO async server
# sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
# app = FastAPI()
# app.mount("/", socketio.ASGIApp(sio))

# # Dictionary to track client tasks
# tasks = {}

# @sio.event
# async def connect(sid, environ, auth):
#     print(f"Client {sid} connected.")
#     await sio.save_session(sid, {'tasks': {}})

# @sio.event
# async def disconnect(sid):
#     print(f"Client {sid} disconnected.")
#     print("TASKS WERE....")
#     print(tasks)
#     tasks_in_progress = tasks.pop(sid, {})
#     for task_id, task in tasks_in_progress.items():
#         task.cancel()
#         try:
#             await task
#         except asyncio.CancelledError:
#             print(f"Task {task_id} for client {sid} was cancelled.")
#     print("TASKS ARE....")
#     print(tasks)

# @sio.event
# async def process_task(sid, data):
#     task_id = data.get('task_id')
#     print(f"Received task from {sid}: {data}")
#     task = asyncio.create_task(long_running_task(sid, data))
#     task.set_name(f"task-{task_id}")
#     if sid in tasks:
#         tasks[sid][task_id] = task
#     else:
#         tasks[sid] = {task_id: task}

# @sio.event
# async def task_acknowledged(sid, task_id):
#     print("ACKNOWLEDGE!!!")
#     print(f"Acknowledgment received for task {task_id} from client {sid}")
#     print("TASKS WERE....")
#     print(tasks)
#     if sid in tasks and task_id in tasks[sid]:
#         tasks[sid].pop(task_id, None)
#         if not tasks[sid]:
#             del tasks[sid]
#     print("TASKS ARE....")
#     print(tasks)

# async def long_running_task(sid, data):
#     task_id = data.get('task_id')
#     print(tasks)
#     try:
#         for i in range(10):  # Example loop to simulate updates
#             await asyncio.sleep(1)  # Sleep to simulate work
#             await sio.emit('task_update', {'progress': i * 10, 'task_id': task_id}, to=sid)
#         await sio.emit('task_complete', {'result': 'Task Completed!', 'task_id': task_id}, to=sid)
#     except asyncio.CancelledError:
#         print(f"Task {data} for client {sid} was cancelled.")
#         await sio.emit('task_error', {'error': 'Task was cancelled', 'task_id': task_id}, to=sid)

# if __name__ == "__main__":
#     uvicorn.run(app, host='0.0.0.0', port=8000)