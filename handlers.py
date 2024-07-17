import asyncio

import modal
from tools import reel
from models import Task

handlers = {
    "reel": reel
}

app = modal.App(
    name="handlers",
    secrets=[
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("mongo-credentials"),
        modal.Secret.from_name("replicate"),
        modal.Secret.from_name("openai"),
        modal.Secret.from_name("elevenlabs"),
    ],   
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libmagic1", "ffmpeg", "wget")
    # .apt_install("git", "git-lfs", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1")
    .pip_install("pyyaml", "elevenlabs", "openai", "instructor", "Pillow", "pydub", 
                 "boto3", "replicate", "python-magic", "python-dotenv", "moviepy")
    .pip_install("bson").pip_install("pymongo")
    .copy_local_dir("../workflows", remote_path="/workflows")
    .copy_local_dir("tools", remote_path="/root/tools")
)

async def _execute(tool_name: str, args: dict):
    handler = handlers[tool_name]
    output = await handler(args)
    return output

@app.function(image=image, timeout=1800)
async def run(tool_name: str, args: dict):
    result = await _execute(tool_name, args)
    return result

@app.function(image=image, timeout=1800)
async def submit(tool_name: str, task: Task):
    task = Task(**task)
    print(task)
    task.update({"status": "running"})
    try:
        output = await _execute(tool_name, task.args)
        task.update({"status": "completed", "result": output})
    except Exception as e:
        print("Task failed", e)
        task.update({"status": "failed", "error": str(e)})

    
@app.local_entrypoint()
def main():
    async def run_example_remote():
        result = await run.remote.aio(
            tool_name="reel",
            args={
                "prompt": "billy and jamie are playing tennis at wimbledon"
            }
        )
        print(result)
    asyncio.run(run_example_remote())


if __name__ == "__main__":
    async def run_example_local():
        handler = handlers["reel"]
        output = await handler({
            "prompt": "A simulation of Mars colliding with Earth",
            "narrator": True,
            "music": True,
            "min_duration": 10
        })
        print(output)
    asyncio.run(run_example_local())