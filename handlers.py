import asyncio
import modal
from datetime import datetime
from functools import wraps


# from modal_tool import task_handler
from tool import Tool
from models import Task, User, task_handler
from tools import handlers

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


async def _execute(tool_name: str, args: dict, user: str = None, env: str = "STAGE"):
    # handler = handlers[tool_name]
    print("GO!!!")
    print(tool_name, args, user, env)
    result = {"ok33": "hello"}
    intermediate_outputs = None
    # result = await handler(args, user, env=env) 
    print("FINAL RESULT", result)
    print("INTERMEDIATE OUTPUTS", intermediate_outputs)
    return result, intermediate_outputs
        

@app.function(image=image, timeout=3600)
async def run(tool_name: str, args: dict, user: str = None):
    result, intermediate_outputs = await _execute(tool_name, args, user)
    return result, intermediate_outputs

# Example usage with both decorators
@app.function(image=image, timeout=3600)
@task_handler
async def submit(tool_name: str, args: dict, user: str = None, env: str = "STAGE"):
    result, intermediate_outputs = await _execute(tool_name, args, user, env=env)
    return result, intermediate_outputs

@app.local_entrypoint()
def main():
    async def run_example_remote():
        result, intermediate_outputs = await run.remote.aio(
            tool_name="reel",
            args={
                "prompt": "billy and jamie are playing tennis at wimbledon",
            }
        )
        print(result)
        print(intermediate_outputs)
    asyncio.run(run_example_remote())


if __name__ == "__main__":
    async def run_example_local():
        # output = await _execute(
        #     tool_name="reel",
        #     args={
        #         "prompt": "Jack and Abey are learning how to code ComfyUI at 204. Jack is from Madrid and plays jazz music",
        #         "narrator": True,
        #         "music": True,
        #         "min_duration": 10
        #     },
        #     user="651c78aea52c1e2cd7de4fff" #"65284b18f8bbb9bff13ebe65"
        # )
        output, intermediate_outputs = await _execute(
            tool_name="news",
            args={
                "subject": "entertainment"
            },
            user="651c78aea52c1e2cd7de4fff" #"65284b18f8bbb9bff13ebe65"
        )
        print(output)
        print(intermediate_outputs)
    asyncio.run(run_example_local())
