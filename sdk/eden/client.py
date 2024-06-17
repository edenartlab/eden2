import os
import asyncio
import websockets
import json
import httpx
from aiofiles import open as aio_open
from pydantic import SecretStr
from typing import Optional


DEFAULT_API_URL = 'edenartlab--tasks-fastapi-app.modal.run'
# DEFAULT_API_URL = 'edenartlab--tasks-fastapi-app-dev.modal.run'
# DEFAULT_API_URL = "127.0.0.1:8000"


class EdenClient:
    def __init__(self):
        self.api_url = DEFAULT_API_URL
        self.api_key = get_api_key()

    def get_or_create_thread(self, thread_name):
        response = asyncio.run(self.async_run("/thread/create", {"name": thread_name}))
        thread_id = response.get("thread_id")
        return thread_id
    
    def chat(self, message, thread_id):
        async def consume_chat():
            return [message async for message in self.async_chat(message, thread_id)]
        return asyncio.run(consume_chat())
    
    def create(self, workflow, args):
        async def consume_create():
            return [message async for message in self.async_create(workflow, args)]
        return asyncio.run(consume_create())

    def train(self, config):
        async def consume_train():
            return [message async for message in self.async_train(config)]
        return asyncio.run(consume_train())

    def upload(self, file_path):
        return asyncio.run(self.async_upload(file_path))

    async def async_chat(self, message, thread_id):
        payload = {
            "message": message,
            "thread_id": thread_id
        }
        async for message_data in self.async_run_ws("/ws/chat", payload):
            yield message_data

    async def async_create(self, workflow, args):
        payload = {
            "workflow": workflow,
            "args": args
        }
        async for task_data in self.async_run_ws("/ws/create", payload):
            yield task_data

    async def async_train(self, config):
        async for task_data in self.async_run_ws("/ws/train", config):
            yield task_data

    async def async_run_ws(self, endpoint, payload):
        uri = f"wss://{self.api_url}{endpoint}"
        headers = {"X-Api-Key": self.api_key}
        try:
            async with websockets.connect(uri, extra_headers=headers) as websocket:                
                await websocket.send(json.dumps(payload))
                async for message in websocket:
                    message_data = json.loads(message)
                    yield message_data
        except websockets.exceptions.ConnectionClosed as e:
           print(f"Connection closed by the server with code: {e.code}")
        except Exception as e:
           print(f"Error: {e}")
        
    async def async_run(self, endpoint, payload):
        uri = f"https://{self.api_url}{endpoint}"
        headers = {"X-Api-Key": self.api_key}
        async with httpx.AsyncClient() as client:
            response = await client.post(uri, headers=headers, json=payload)
        return response.json()

    async def async_upload(self, file_path):
        async with aio_open(file_path, "rb") as f:
            media = await f.read()
            headers = {"x-api-key": self.api_key}
            files = {"media": ("media", media)}
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://staging.api.eden.art/media/upload",
                    headers=headers,
                    files=files,
                )
            return response.json()


def get_api_key() -> SecretStr:
    if os.getenv("EDEN_API_KEY"):
        return SecretStr(os.getenv("EDEN_API_KEY"))
    home_dir = os.path.expanduser("~")
    api_key_file = os.path.join(home_dir, ".eden")
    try:
        with open(api_key_file, "r") as file:
            api_key = file.read().strip()
        return SecretStr(api_key)
    except FileNotFoundError:
        raise Exception("\033[91mNo EDEN_API_KEY found. Please set it in your environment or run `eden login` to save it in your home directory.\033[0m")
