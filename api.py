import modal
from typing import Optional
from bson.objectid import ObjectId
from fastapi import FastAPI, HTTPException
from starlette.websockets import WebSocketState
from bson import ObjectId
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, Any, Optional
from pydantic import BaseModel
# from functools import wraps
from starlette.websockets import WebSocketDisconnect, WebSocketState
# from thread import Thread, UserMessage, AssistantMessage
from pydantic import BaseModel
from pydantic.json_schema import SkipJsonSchema

import auth
from mongo import threads, tasks, users, models
from thread import UserMessage
# from endpoint import tools, endpoint_summary

import replicate

from mongo import MongoBaseModel, models, tasks
import s3

from typing import List
from pydantic import BaseModel, Field
from bson import ObjectId




class Model(MongoBaseModel):
    name: str
    user: ObjectId
    slug: str = None
    public: bool = False
    checkpoint: str
    training_images: List[str] = Field([], description="The training images used to train the model")
    thumbnail: str

    def __init__(self, **data):
        super().__init__(**data)
        self.make_slug()

    def make_slug(self):
        name = self.name.lower().replace(" ", "-")
        version_count = 1 + models.count_documents({"name": self.name, "user": self.user}) 
        username = users.find_one({"_id": self.user})["username"]
        self.slug = f"{name}/{username}/v{version_count}"

    def save(self):
        Model.save(self.to_mongo(), models)


class Task(MongoBaseModel):
    workflow: str
    args: Dict[str, Any]
    status: str = "pending"
    error: Optional[str] = None
    result: Optional[str] = None
    public: bool = False
    user: ObjectId

    def save(self):
        Task.save(self.to_mongo(), tasks)


def create_handler(task_handler):
    async def websocket_handler(
        websocket: WebSocket, 
        user: dict = Depends(auth.authenticate_ws)
    ):
        await websocket.accept()
        try:
            async for data in websocket.iter_json():
                try:
                    async for response in task_handler(data, user):
                        await websocket.send_json(response)
                    break
                except Exception as e:
                    await websocket.send_json({"error": str(e)})
                    break
        except WebSocketDisconnect:
            print("WebSocket disconnected by client")
        finally:
            if websocket.application_state == WebSocketState.CONNECTED:
                print("Closing WebSocket...")
                await websocket.close()
    return websocket_handler



# class CreateRequest(BaseModel):
#     workflow: str
#     config: Dict[str, Any]

class Task(MongoBaseModel):
    workflow: str
    args: Dict[str, Any]
    status: str = "pending"
    error: Optional[str] = None
    result: Optional[str] = None
    public: bool = False
    user: ObjectId

    def save(self):
        Task.save(self.to_mongo(), tasks)


async def create(data, user):
    print("go get here")
    print(data)
    print("lets go")
    print(user)
    print(user["_id"])
    task = Task(**data, user=user["_id"])
    print("TAKS IS", task)
    yield task.model_dump_json()
    
    # args = {
    #     "look_image": "https://i.ytimg.com/vi/AkKx4Fn02iM/maxresdefault.jpg",
    #     "prompt": "a professional photo of embedding:SDXL_embeddings_xander",
    #     "lora": "https://edenartlab-stage-data.s3.amazonaws.com/0abbfd2c6b8ae837d013640b88a64510085d4439bc9510878e72df64fe2fc0b1.tar"
    # }
    print(task)
    cls = modal.Cls.lookup("comfyui", task.workflow)
    print(cls)
    result = cls().api.remote(task.args)
    print("THE RESULT", result)

    # cls = modal.Cls.lookup("comfyui-dev", "xhibit")
    # result = cls().api.remote(args)

    if 'error' in result:
        task.status = "failed"
        task.error = str(result['error'])
    else:
        task.status = "completed"
        task.result = result
    
    # Task.save(task, tasks)
    yield task.model_dump_json()
    # yield result



class TrainRequest(BaseModel):
    name: str
    training_images: List[str]
    mode: str = "face"
    base_model: str = "sdxl"


async def train(config: Dict, user):
    print("GOT A CONFIG", config)
    print("c1")
    request = TrainRequest(**config)
    print("c2")
    print(request)

    

        
    deployment = replicate.deployments.get("edenartlab/lora-trainer")
    prediction = deployment.predictions.create(
        input={
            "name": request.name,
            "lora_training_urls": "|".join(request.training_images), 
            # "ti_lr": 0.001,
            # "unet_lr": 0.001,
            # "n_tokens": 2,
            # "use_dora": False,
            # "lora_rank": 16,
            # "resolution": 512,
            "concept_mode": request.mode,
            # "max_train_steps": 400,
            "sd_model_version": request.base_model,
            # "train_batch_size": 4
        }
    )

    prediction.wait()
    output = prediction.output[-1]

    if not output.get('files'):
        raise Exception("No files found in output")
    
    tarfile = output['files'][0]
    thumbnail = output['thumbnails'][0]
    
    tarfile_url = s3.upload_file_from_url(tarfile)
    thumbnail_url = s3.upload_file_from_url(thumbnail)
    print("tarfile_url", tarfile_url)
    print("thumbnail_url", thumbnail_url)
    print("USER!!!!")
    print(user)
    model = Model(
        name=request.name,
        user=user["_id"],
        checkpoint=tarfile_url, 
        training_images=request.training_images,
        thumbnail=thumbnail_url
    )

    Model.save(model, models)

    yield {
        "task_id": "taskid",
        "result": model.id,
    }





class ChatRequest(BaseModel):
    message: UserMessage
    thread_id: Optional[str] = None

async def chat(data, user):
    request = ChatRequest(**data)

    if request.thread_id:
        thread = threads.find_one({"_id": ObjectId(request.thread_id)})
        if not thread:
            # await websocket.send_json({"error": "Thread ID not found"})
            raise Exception("Thread ID not found")
        thread = Thread(**thread, tools=tools)
    else:
        thread = Thread(system_message=default_system_message, tools=tools)

    async for response in thread.prompt(request.message):
        yield {
            "thread_id": str(thread.id),
            "message": response.model_dump_json()
        }









web_app = FastAPI()

web_app.websocket("/ws/create")(create_handler(create))
web_app.websocket("/ws/chat")(create_handler(chat))
web_app.websocket("/ws/train")(create_handler(train))

import modal

app = modal.App(
    name="tasks",
    secrets=[
        modal.Secret.from_name("s3-credentials"),
        modal.Secret.from_name("clerk-credentials"),
        modal.Secret.from_name("mongo-credentials"),
        modal.Secret.from_name("openai"),
        modal.Secret.from_name("replicate"),
    ],
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1-mesa-glx", "libglib2.0-0", "libmagic1")
    .pip_install("pyjwt", "httpx", "cryptography", "pymongo", "instructor==1.2.6", "fastapi==0.103.1", "pyyaml", "python-dotenv", "python-socketio", "replicate", "boto3", "python-magic") #, "tqdm")
    .copy_local_dir("../workflows", remote_path="/root/workflows")
    .pip_install("requests", "Pillow")
    # .copy_local_file("agent2.py", remote_path="/root/agent2.py")
)
    
with image.imports():
    from thread import Thread, UserMessage
    from endpoint import get_tools, get_tools_summary
    tools = get_tools("/root/workflows")
    tools_summary = get_tools_summary(tools)
    default_system_message = (
        "You are an assistant who is an expert at using Eden. "
        "You have the following tools available to you: "
        "\n\n---\n{tools_summary}\n---"
        "\n\nIf the user clearly wants you to make something, select exactly ONE of the tools. Do NOT select multiple tools. Do NOT hallucinate any tool, especially do not use 'multi_tool_use' or 'multi_tool_use.parallel.parallel'. Only tools allowed: {tool_names}." 
        "If the user is just making chat with you or asking a question, leave the tool null and just respond through the chat message. "
        "If you're not sure of the user's intent, you can select no tool and ask the user for clarification or confirmation. " 
        "Look through the whole conversation history for clues as to what the user wants. If they are referencing previous outputs, make sure to use them."
    ).format(tools_summary=tools_summary, tool_names=', '.join([t for t in tools]))

@app.function(
    image=image, 
    keep_warm=0,
    concurrency_limit=5,
    timeout=600,
    container_idle_timeout=30,
)
@modal.asgi_app()
def fastapi_app():
    return web_app
