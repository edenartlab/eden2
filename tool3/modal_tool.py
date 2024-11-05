import asyncio
import modal
from typing import Dict
from functools import wraps
from datetime import datetime

from models import Task, User, task_handler_func
from tools import handlers
from tool import Tool
import eden_utils


class ModalTool(Tool):
    @Tool.handle_run
    async def async_run(self, args: Dict, env: str):
        func = modal.Function.lookup("handlers2", "run")
        result = await func.remote.aio(tool_key=self.key, args=args, env=env)
        return result

    # @Tool.handle_submit
    async def async_start_task(self, task: Task):
        func = modal.Function.lookup("handlers2", "run_task")
        job = func.spawn(task)
        return job.object_id
    
    @Tool.handle_wait
    async def async_wait(self, task: Task):
        if not task.handler_id:
            task.reload()
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        await fc.get.aio()
        task.reload()
        return task.result
    
    @Tool.handle_cancel
    async def async_cancel(self, task: Task):
        fc = modal.functions.FunctionCall.from_id(task.handler_id)
        await fc.cancel.aio()


app = modal.App(
    name="handlers2",
    secrets=[
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("mongo-credentials"),
        # modal.Secret.from_name("replicate"),
        # modal.Secret.from_name("openai"),
        # modal.Secret.from_name("anthropic"),
        # modal.Secret.from_name("elevenlabs"),
        # modal.Secret.from_name("newsapi"),
        # modal.Secret.from_name("runway"),
        # modal.Secret.from_name("sentry"),
    ],   
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libmagic1", "ffmpeg", "wget")
    .pip_install("pyyaml", "elevenlabs", "openai", "httpx", "cryptography", "pymongo", "instructor[anthropic]", "anthropic",
                 "instructor", "Pillow", "pydub", "sentry_sdk", "pymongo", "runwayml", "google-api-python-client",
                 "boto3", "replicate", "python-magic", "python-dotenv", "moviepy")
)

@app.function(image=image, timeout=3600)
async def run(tool_key: str, args: dict, env: str):
    result = await handlers[tool_key](args, env=env)
    return eden_utils.upload_result(result, env=env)

@app.function(image=image, timeout=3600)
@task_handler_func
async def run_task(tool_key: str, args: dict, env: str):
    return await handlers[tool_key](args, env=env)


if __name__ == "__main__":
    async def run_example_local():
        return await run(
            tool_key="tool2", args={"subject": "entertainment"}, env="STAGE"
        )        
    print(asyncio.run(run_example_local()))
