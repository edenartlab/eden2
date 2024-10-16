import dotenv
dotenv.load_dotenv()

import asyncio
import modal
from datetime import datetime
from tools import reel, story, news, chat, runway
from tools import write
from models import Task, User, Story
import eden_utils

handlers = {
    "reel": reel,
    "story": story,
    "news": news,
    "write": write,
    "chat": chat,
    "runway": runway
}

app = modal.App(
    name="handlers",
    secrets=[

        modal.Secret.from_name("admin-key"),
        modal.Secret.from_name("clerk-credentials"), # ?
        
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("mongo-credentials"),
        modal.Secret.from_name("replicate"),
        modal.Secret.from_name("openai"),
        modal.Secret.from_name("anthropic"),
        modal.Secret.from_name("elevenlabs"),
        modal.Secret.from_name("newsapi"),
        modal.Secret.from_name("runway"),
        modal.Secret.from_name("sentry"),
    ],   
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libmagic1", "ffmpeg", "wget")
    .pip_install("pyyaml", "elevenlabs", "openai", "httpx", "cryptography", "pymongo", "instructor[anthropic]", "anthropic",
                 "instructor", "Pillow", "pydub", "sentry_sdk", "pymongo", "runwayml", "google-api-python-client",
                 "boto3", "replicate", "python-magic", "python-dotenv", "moviepy")
    # .pip_install("bson").pip_install("pymongo")
    .copy_local_dir("../workflows", remote_path="/workflows")
    .copy_local_dir("../private_workflows", remote_path="/private_workflows")
    .copy_local_dir("tools", remote_path="/root/tools")
)


async def _execute(tool_name: str, args: dict, user: str = None, env: str = "STAGE"):
    handler = handlers[tool_name]
    result = await handler(args, user, env=env)
    return result
        

@app.function(image=image, timeout=3600)
async def run(tool_name: str, args: dict, user: str = None):
    result = await _execute(tool_name, args, user)
    return result


@app.function(image=image, timeout=3600)
async def submit(task_id: str, env: str):
    task = Task.from_id(document_id=task_id, env=env)
    print(task)
    
    start_time = datetime.utcnow()
    queue_time = (start_time - task.createdAt).total_seconds()
    
    task.update({
        "status": "running",
        "performance": {"waitTime": queue_time}
    })

    try:
        output = await _execute(
            task.workflow, task.args, task.user, env=env
        )
        if task.output_type == "string":
            result = output
            print(output)
            print(Story)
            story = Story.from_id("66de2dfa5286b9dc656291c1", env=env)
            story.update(output)
        elif task.output_type == "message":
            result = output
        else:
            result = eden_utils.upload_media(output, env=env)
        print(result)
        task_update = {
            "status": "completed", 
            "result": result
        }
        return task_update

    except Exception as e:
        print("Task failed", e)
        task_update = {"status": "failed", "error": str(e)}
        user = User.from_id(task.user, env=env)
        user.refund_manna(task.cost or 0)

    finally:
        run_time = datetime.utcnow() - start_time
        task_update["performance.runTime"] = run_time.total_seconds()
        task.update(task_update)

    
@app.local_entrypoint()
def main():
    async def run_example_remote():
        result = await run.remote.aio(
            tool_name="reel",
            args={
                "prompt": "billy and jamie are playing tennis at wimbledon",
            }
        )
        print(result)
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
        output = await _execute(
            tool_name="news",
            args={
                "subject": "entertainment"
            },
            user="651c78aea52c1e2cd7de4fff" #"65284b18f8bbb9bff13ebe65"
        )
        print(output)
    asyncio.run(run_example_local())