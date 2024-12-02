import os
import modal
import asyncio
import json
from bson import ObjectId
from typing import Optional
from pydantic import BaseModel
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    HTTPException,
    Request,
    BackgroundTasks,
)
from starlette.websockets import WebSocketDisconnect, WebSocketState
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials

# import auth
# from agent import Agent
# from thread import Thread, UserMessage, async_prompt, prompt
# from models import Task

from eve import auth
from eve.tool import Tool, get_tools_from_mongo
from eve.llm import UserMessage, async_prompt_thread
from eve.thread import Thread


db = os.getenv("DB", "STAGE")
if db not in ["PROD", "STAGE"]:
    raise Exception(f"Invalid environment: {db}. Must be PROD or STAGE")
app_name = "tools-new" if db == "PROD" else "tools-new-dev"

client = AsyncOpenAI()

api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


async def chat_stream(request: Request):
    # Parse the incoming JSON
    data = await request.json()

    async def generate():
        stream = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": data["content"]}],
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield f"{chunk.choices[0].delta.content}\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )



def task_handler(
    request: dict,
    _: dict = Depends(auth.authenticate_admin)
):
    tool_name = request.get("tool")
    user_id = request.get("user_id")
    args = request.get("args")

    async def submit_task():
        tool = Tool.load(tool_name, db=db)
        task = await tool.async_start_task(user_id, args, db=db)
        return task

    return asyncio.run(submit_task())



async def chat_handler(
    request: dict,
    background_tasks: BackgroundTasks,
    _: dict = Depends(auth.authenticate_admin)
):
    user_id = request.get("user_id")
    agent_id = request.get("agent_id")
    thread_id = request.get("thread_id")
    user_message = UserMessage(**request.get("user_message"))

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
    


web_app = FastAPI()

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

web_app.post("/create")(task_handler)
web_app.post("/chat")(chat_handler)
web_app.post("/chat/stream")(chat_stream)


app = modal.App(
    name=app_name,
    secrets=[
        modal.Secret.from_name("admin-key"),
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("mongo-credentials"),
        modal.Secret.from_name("replicate"),
        modal.Secret.from_name("openai"),
        modal.Secret.from_name("anthropic"),
        modal.Secret.from_name("elevenlabs"),
        modal.Secret.from_name("hedra"),
        modal.Secret.from_name("newsapi"),
        modal.Secret.from_name("runway"),
        modal.Secret.from_name("sentry"),
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
