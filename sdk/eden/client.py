import os
import asyncio
import websockets
import json
from pydantic import SecretStr
from typing import Optional


#DEFAULT_API_URL = 'https://edenartlab--tasks-fastapi-app-dev.modal.run'
DEFAULT_API_URL = 'edenartlab--tasks-fastapi-app-dev.modal.run'
# DEFAULT_API_URL = "127.0.0.1:8000"


class EdenClient:
    def __init__(self):
        self.api_url = DEFAULT_API_URL
        self.api_key = get_api_key()

    def chat(self, message, thread_id):
        async def consume_chat():
            return [message async for message in self.async_chat(message, thread_id)]
        return asyncio.run(consume_chat())
    
    def create(self, endpoint, config):
        async def consume_create():
            return [message async for message in self.async_create(endpoint, config)]
        return asyncio.run(consume_create())

    async def async_chat(self, message, thread_id):
        payload = {
            "message": message,
            "thread_id": thread_id
        }
        async for message_data in self.async_run("/ws/chat", payload):
            yield message_data

    async def async_create(self, endpoint, config):
        payload = {
            "endpoint": endpoint,
            "config": config
        }
        async for task_data in self.async_run("/ws/create", payload):
            yield task_data

    async def async_run(self, endpoint, payload):
        uri = f"wss://{self.api_url}{endpoint}"
        headers = {"X-Api-Key": self.api_key}
        print("RUN", payload)
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
        return None




################################################################################
################################################################################
################################################################################
## SOCKET IO

# import re
# import os
# import json
# import socketio
# import asyncio
# from rich.console import Console
# from rich.progress import Progress, SpinnerColumn, TextColumn
# from pydantic import BaseModel, SecretStr
# from typing import Dict, Any, Optional
# from thread import Thread, UserMessage, AssistantMessage


# DEFAULT_API_URL = 'https://edenartlab--tasks-fastapi-app-dev.modal.run'


# class EdenClient:
#     def __init__(self):
#         self.api_url = (os.getenv("EDEN_API_URL") or DEFAULT_API_URL)
#         self.api_key = get_api_key()
        
#         self.sio = socketio.AsyncClient()
#         self.task_queue = asyncio.Queue()

#         @self.sio.event
#         async def connect():
#             pass

#         @self.sio.event
#         async def disconnect():
#             pass

#         @self.sio.event
#         async def task_update(data):
#             await self.task_queue.put(("update", data))

#         @self.sio.event
#         async def task_complete(data):
#             await self.task_queue.put(("complete", data))

#         @self.sio.event
#         async def task_error(data):
#             await self.task_queue.put(("error", data))

#         @self.sio.event
#         async def auth_error(data):
#             await self.task_queue.put(("auth_error", data))

#     async def __aenter__(self):
#         return self

#     async def __aexit__(self, exc_type, exc_value, traceback):
#         await self.sio.disconnect()
#         await self.sio.wait()

#     def chat(self, *args):
#         async def return_whole_chat():
#             return [message async for message in self.async_chat(*args)]
#         return asyncio.run(return_whole_chat())
    
#     async def async_chat_mock(self, message, thread_id):
#         yield {'task_id': '664c3bc3567aaf8b7fbf0663', 'message': '{"role":"assistant","content":null,"function_call":null,"tool_calls":[{"id":"call_M1UVtlU6GFlcqesIHKnldMft","function":{"arguments":"{\\"prompt\\": \\"A cute picture of a cat\\", \\"negative_prompt\\": \\"Abstract background\\", \\"width\\": 512, \\"height\\": 512, \\"seed\\": 24680}","name":"txt2img"},"type":"function"}]}'}
#         yield {'task_id': '664c3bc3567aaf8b7fbf0663', 'message': '{"role":"tool","name":"txt2img","content":"https://edenartlab-stage-data.s3.amazonaws.com/1522d1efdc32518c8ab9ac4cd21f8f74bab80c6ded900d95709bb161081d1321.jpg","tool_call_id":"call_M1UVtlU6GFlcqesIHKnldMft"}'}

#     async def async_chat(self, message, thread_id):
#         if not self.sio.connected:
#             await self.sio.connect(self.api_url, headers={"X-Api-Key": self.api_key.get_secret_value()})

#         await self.sio.emit('chat', {
#             "message": message,
#             "thread_id": thread_id
#         })

#         while True:
#             event_type, data = await self.task_queue.get()
#             if event_type in ['complete', 'error', 'auth_error']:
#                 break
#             yield data

#         await self.sio.disconnect()


# def get_api_key() -> Optional[SecretStr]:
#     if os.getenv("EDEN_API_KEY"):
#         return SecretStr(os.getenv("EDEN_API_KEY"))
#     home_dir = os.path.expanduser("~")
#     api_key_file = os.path.join(home_dir, ".eden")
#     try:
#         with open(api_key_file, "r") as file:
#             api_key = file.read().strip()
#         return SecretStr(api_key)
#     except FileNotFoundError:
#         return None
