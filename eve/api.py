import os
from fastapi.responses import StreamingResponse
import modal
from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from fastapi.security import APIKeyHeader, HTTPBearer
from pydantic import BaseModel
import json

from eve import auth
from eve.tool import Tool, get_tools_from_mongo
from eve.llm import UpdateType, UserMessage, async_prompt_thread

# Config setup
db = os.getenv("DB", "STAGE")
if db not in ["PROD", "STAGE"]:
    raise Exception(f"Invalid environment: {db}. Must be PROD or STAGE")
app_name = "tools" if db == "PROD" else "tools-dev"

client = AsyncOpenAI()
api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)
background_tasks: BackgroundTasks = BackgroundTasks()


class TaskRequest(BaseModel):
    workflow: str
    args: dict | None = None
    user: str | None = None


class ChatRequest(BaseModel):
    user_message: dict
    thread_name: str


async def handle_task(workflow: str, user: str, args: dict | None = None) -> dict:
    tool = Tool.load(workflow, db=db)
    return await tool.async_start_task(user, args or {}, db=db)


async def handle_chat(
    user_id: str,
    user_message: str,
    thread_name: str,
) -> dict:
    tools = get_tools_from_mongo(db=db)

    async def run_prompt():
        async for _ in async_prompt_thread(
            db=db,
            user_id=user_id,
            thread_name=thread_name,
            user_messages=user_message,
            tools=tools,
        ):
            pass

    background_tasks.add_task(run_prompt)
    return {"status": "success"}


# FastAPI app setup
web_app = FastAPI()
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@web_app.post("/admin/create")
async def task_admin(request: TaskRequest, _: dict = Depends(auth.authenticate_admin)):
    return await handle_task(request.workflow, request.user, request.args)


@web_app.post("/create")
async def task(request: TaskRequest, auth: dict = Depends(auth.authenticate)):
    return await handle_task(request.workflow, auth.userId, request.args)


@web_app.post("/chat")
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
