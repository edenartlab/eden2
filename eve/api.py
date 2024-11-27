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
)
from starlette.websockets import WebSocketDisconnect, WebSocketState
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from fastapi.responses import StreamingResponse

# import auth
# from agent import Agent
# from thread import Thread, UserMessage, async_prompt, prompt
# from models import Task

from eve import auth
from eve.tool import Tool
from eve.task import Task
from eve.llm import Thread


db = os.getenv("DB", "STAGE")
if db not in ["PROD", "STAGE"]:
    raise Exception(f"Invalid environment: {db}. Must be PROD or STAGE")
app_name = "tools" if db == "PROD" else "tools-dev"

client = AsyncOpenAI()


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
    # _: dict = Depends(auth.authenticate_admin)
):
    workflow = request.get("workflow")
    user = request.get("user")
    args = request.get("args")

    async def submit_task():
        tool = Tool.load(workflow, db=db)
        task = await tool.async_start_task(user, args, db="STAGE")
        return task

    return asyncio.run(submit_task())


def task_handler_authenticated(
    request: dict,
    auth: dict = Depends(auth.authenticate),  # bring auth back later
):
    workflow = request.get("workflow")
    user = auth.userId
    args = request.get("args")

    async def submit_task():
        tool = Tool.load(workflow, db=db)
        task = await tool.async_start_task(user, args, db="STAGE")
        return task

    return asyncio.run(submit_task())


web_app = FastAPI()

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

web_app.post("/create")(task_handler)
web_app.post("/create-authenticated")(task_handler_authenticated)
web_app.post("/chat/stream")(chat_stream)


app = modal.App(
    name=app_name,
    secrets=[
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
    .env({"ENV": db, "MODAL_SERVE": os.getenv("MODAL_SERVE")})
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
