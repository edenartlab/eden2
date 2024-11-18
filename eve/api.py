import os
import modal
import asyncio
import json
from bson import ObjectId
from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request
from starlette.websockets import WebSocketDisconnect, WebSocketState

#import auth
#from agent import Agent
#from thread import Thread, UserMessage, async_prompt, prompt
# from models import Task

from eve.tool import Tool
from eve.task import Task
from eve.llm import Thread


db = os.getenv("DB", "STAGE")
if db not in ["PROD", "STAGE"]:
    raise Exception(f"Invalid environment: {db}. Must be PROD or STAGE")
app_name = "tools" if db == "PROD" else "tools-dev"



def task_handler(
    request: dict, 
    # _: dict = Depends(auth.authenticate_admin)  # bring auth back later
):
    workflow = request.get("workflow")
    user = request.get("user")
    args = request.get("args")

    async def submit_task():
        tool = Tool.load(workflow, db=db)
        task = await tool.async_start_task(user, args, db="STAGE")
        return task
    
    return asyncio.run(submit_task())



web_app = FastAPI()

web_app.post("/create")(task_handler)


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
    .pip_install("pyyaml", "elevenlabs", "openai", "httpx", "cryptography", "pymongo", "instructor[anthropic]", "anthropic",
                 "instructor", "Pillow", "pydub", "sentry_sdk", "pymongo", "runwayml", "google-cloud-aiplatform",
                 "boto3", "replicate", "python-magic", "python-dotenv", "moviepy",
                 "fastapi>=0.100.0", "pydantic>=2.0.0")
)

@app.function(
    image=image, 
    keep_warm=1,
    concurrency_limit=10,
    container_idle_timeout=60,
    timeout=3600
)
@modal.asgi_app()
def fastapi_app():
    return web_app
