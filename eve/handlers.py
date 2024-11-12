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
                 "instructor", "Pillow", "pydub", "sentry_sdk", "pymongo", "runwayml", "google-api-python-client", "google-cloud-aiplatform",
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

<<<<<<< HEAD
=======
    try:
        output = await _execute(
            task.workflow, task.args, task.user, env=env
        )

        if task.output_type == "string":
            result = output
            # print(output)
            # print(Story)
            # story = Story.from_id("66de2dfa5286b9dc656291c1", env=env)
            # story.update(output)
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

    
>>>>>>> abd66b1fafce84c83ecd41a1f4312cbd1a70982d
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
    import os
    import argparse
    from config import get_all_tools_from_yaml
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--tool', type=str, help='Name of the tool to run')
    args = parser.parse_args()

    if args.tool not in handlers:
        raise ValueError(f"Tool {args.tool} not in modal handlers")
    
    tool = get_all_tools_from_yaml()[args.tool]

    async def run_example_local():
<<<<<<< HEAD
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
=======
        result = await _execute(
            tool_name=args.tool,
            args=tool.test_args,
            user=os.getenv("EDEN_TEST_USER_STAGE")
        )
        print(result)
        return result
    asyncio.run(run_example_local())
>>>>>>> abd66b1fafce84c83ecd41a1f4312cbd1a70982d
