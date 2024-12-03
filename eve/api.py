import os
from fastapi.responses import StreamingResponse
import modal
from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from fastapi.security import APIKeyHeader, HTTPBearer
from pydantic import BaseModel
from typing import Optional
import json

from eve import auth
from eve.tool import Tool, get_tools_from_mongo
from eve.llm import UpdateType, UserMessage, async_prompt_thread
from eve.thread import Thread

# Config setup
db = os.getenv("DB", "STAGE").upper()
if db not in ["PROD", "STAGE"]:
    raise Exception(f"Invalid environment: {db}. Must be PROD or STAGE")
app_name = "tools-new" if db == "PROD" else "tools-new-dev"

client = AsyncOpenAI()
api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)
background_tasks: BackgroundTasks = BackgroundTasks()



class TaskRequest(BaseModel):
    tool: str
    args: dict
    user_id: str

class ChatRequest(BaseModel):
    user_id: str
    agent_id: str
    thread_id: Optional[str] = None
    user_message: dict

# FastAPI app setup
web_app = FastAPI()
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# web_app.post("/create")(task_handler)
# web_app.post("/chat")(chat_handler)
# web_app.post("/chat/stream")(chat_stream)

async def handle_task(tool: str, user_id: str, args: dict = {}) -> dict:
    tool = Tool.load(tool, db=db)
    return await tool.async_start_task(user_id, args, db=db)

@web_app.post("/create")
async def task_admin(request: TaskRequest): #, _: dict = Depends(auth.authenticate_admin)):
    return await handle_task(request.tool, request.user_id, request.args)

# @web_app.post("/create")
# async def task(request: TaskRequest): #, auth: dict = Depends(auth.authenticate)):
#     return await handle_task(request.tool, auth.userId, request.args)

@web_app.post("/chat")
async def handle_chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    # _: dict = Depends(auth.authenticate_admin)
):
    user_id = request.user_id
    agent_id = request.agent_id
    thread_id = request.thread_id
    user_message = UserMessage(**request.user_message)

    tools = get_tools_from_mongo(db=db)
    
    if not thread_id:
        thread_new = Thread.create(
            db=db,
            user=user_id,
            agent=agent_id,
        )
        thread_id = str(thread_new.id)

    try:
        async def run_prompt():
            async for _ in async_prompt_thread(
                db=db,
                user_id=user_id,
                agent_id=agent_id,
                thread_id=thread_id,
                user_messages=user_message,
                tools=tools
            ):
                pass
        
        background_tasks.add_task(run_prompt)        
        return {"status": "success", "thread_id": thread_id}
    
    except Exception as e:
        print(e)
        return {"status": "error", "message": str(e)}
    

@web_app.post("/chat_and_wait")
async def stream_chat(
    request: ChatRequest,
    auth: dict = Depends(auth.authenticate),
):
    user_messages = UserMessage(**request.user_message)

    async def event_generator():
        async for update in async_prompt_thread(
            db=db,
            user_id=auth.userId,
            thread_name=request.thread_name,
            user_messages=UserMessage(**request.user_message),
            tools=get_tools_from_mongo(db=db),
            provider="anthropic",
        ):
            if update.type == UpdateType.ASSISTANT_MESSAGE:
                data = {
                    "type": str(update.type),
                    "content": update.message.content,
                }
            elif update.type == UpdateType.TOOL_COMPLETE:
                data = {
                    "type": str(update.type),
                    "tool": update.tool_name,
                    "result": update.result,
                }
            else:
                data = {
                    "type": "error",
                    "error": update.error or "Unknown error occurred",
                }

            yield f"data: {json.dumps({'event': 'update', 'data': data})}\n\n"

        yield f"data: {json.dumps({'event': 'done', 'data': ''})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Modal app setup
app = modal.App(
    name=app_name,
    secrets=[
        modal.Secret.from_name(s)
        for s in [
            "admin-key",
            "s3-credentials",
            "mongo-credentials",
            "replicate",
            "openai",
            "anthropic",
            "elevenlabs",
            "hedra",
            "newsapi",
            "runway",
            "sentry",
        ]
    ],
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .env({"DB": db, "MODAL_SERVE": os.getenv("MODAL_SERVE")})
    .apt_install("libmagic1", "ffmpeg", "wget")
    .pip_install_from_pyproject("../pyproject.toml")
)

@app.function(
    image=image,
    keep_warm=1,
    concurrency_limit=10,
    container_idle_timeout=60,
    timeout=3600,
)
@modal.asgi_app()
def fastapi_app():
    return web_app
