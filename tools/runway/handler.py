import sys
sys.path.append("../..")
import time
from runwayml import RunwayML

client = RunwayML()

async def runway(args: dict, user: str = None, env: str = None):
    task = client.image_to_video.create(
    model='gen3a_turbo',
        prompt_image=args["prompt_image"],
        prompt_text=args["prompt_text"]
    )
    task_id = task.id
    print(task_id)

    time.sleep(10)
    task = client.tasks.retrieve(task_id)
    while task.status not in ['SUCCEEDED', 'FAILED']:
        print("status", task.status)
        time.sleep(10)  # Wait for ten seconds before polling
        task = client.tasks.retrieve(task_id)
    
    # TODO: callback for running state

    if task.status == "FAILED":
        print("Error", task.failure)
        raise Exception(task.failure)
    
    return [task.output[0]]