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
    async def async_run(self, args: Dict, env="STAGE"):
        func = modal.Function.lookup("handlers2", "run")
        result = await func.remote.aio(tool_key=self.key, args=args)
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
        # modal.Secret.from_name("admin-key"),
        # modal.Secret.from_name("clerk-credentials"), # ?
        
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
    # .copy_local_dir("../workflows", remote_path="/workflows")
    # .copy_local_dir("../private_workflows", remote_path="/private_workflows")
    # .copy_local_dir("tools", remote_path="/root/tools")
)

@app.function(image=image, timeout=3600)
async def run(tool_key: str, args: dict, env: str):
    result = await handlers[tool_key](args, env)
    return eden_utils.prepare_result(result, env="STAGE")


@app.function(image=image, timeout=3600)
@task_handler_func
async def run_task(tool_key: str, args: dict, env: str):
    return await handlers[tool_key](args, env=env)


if __name__ == "__main__":
    import asyncio
    async def run_example_local():
        # output = await _execute(
        #     tool_key="reel",
        #     args={
        #         "prompt": "Jack and Abey are learning how to code ComfyUI at 204. Jack is from Madrid and plays jazz music",
        #         "narrator": True,
        #         "music": True,
        #         "min_duration": 10
        #     },
        #     user="651c78aea52c1e2cd7de4fff" #"65284b18f8bbb9bff13ebe65"
        # )
        output = await run_task(
            tool_key="tool2",
            args={
                "subject": "entertainment"
            },
            user="651c78aea52c1e2cd7de4fff" #"65284b18f8bbb9bff13ebe65"
        )
        print(output)
        
    asyncio.run(run_example_local())
