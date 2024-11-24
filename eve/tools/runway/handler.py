import time
from runwayml import RunwayML




async def handler(args: dict, db: str):
    client = RunwayML()

    task = client.image_to_video.create(
        model='gen3a_turbo',
        prompt_image=args["prompt_image"],
        prompt_text=args["prompt_text"][:512]
    )
    task_id = task.id
    print(task_id)

    time.sleep(10)
    task = client.tasks.retrieve(task_id)
    while task.status not in ['SUCCEEDED', 'FAILED']:
        print("status", task.status)
        time.sleep(10) 
        task = client.tasks.retrieve(task_id)
    
    # TODO: callback for running state

    if task.status == "FAILED":
        print("Error", task.failure)
        raise Exception(task.failure)
    
    return {
        "output": task.output[0]
    }
