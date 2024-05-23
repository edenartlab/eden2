import os
import httpx
from httpx import Timeout
import asyncio
import websockets
import json
from pydantic import SecretStr
from pydantic import BaseModel
from typing import Dict, Any, Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

#DEFAULT_API_URL = "https://edenartlab--tasks-fastapi-app-dev.modal.run"
DEFAULT_API_URL = "https://edenartlab--tasks-fastapi-app.modal.run"
DEFAULT_API_URL = "https://edenartlab--tasks-fastapi-app-dev.modal.run"
print("THE DEFAULT API URL IS", DEFAULT_API_URL)

class WorkflowRequest(BaseModel):
    workflow: str
    config: Dict[str, Any]

class UserMessage(BaseModel):
    content: str
    metadata: Optional[Dict[str, Any]] = {}
    attachments: Optional[list[Dict[str, Any]]] = []


class EdenClient:
    def __init__(self):
        self.api_url = (os.getenv("EDEN_API_URL") or DEFAULT_API_URL)
        self.ssl = self.api_url.startswith("https://")
        self.api_url = self.api_url.lstrip("http://").lstrip("https://")
        self.api_key = get_api_key()
        self.console = Console()

    def run(self, *args):
        return asyncio.run(self.async_run(*args))

    def chat(self, *args):
        async def consume_chat():
            return [message async for message in self.async_chat(*args)]
        return asyncio.run(consume_chat())
    
    async def async_run(
        self, 
        workflow: str, 
        config: Dict[str, Any]
    ):
        self.console.print("[bold yellow]Pending...", end="")
        headers = {"X-Api-Key": self.api_key}
        ws = "wss" if self.ssl else "ws"
        async with websockets.connect(
            f"{ws}://{self.api_url}/ws/tasks/run", 
            extra_headers=headers
        ) as websocket:
            data = {
                "workflow": workflow, 
                "config": config
            }
            await websocket.send(json.dumps(data))
            
            with Progress(
                SpinnerColumn(), 
                TextColumn("[bold cyan]Running..."), 
                transient=True,
                console=self.console
            ) as progress:
                task = progress.add_task("[cyan]Connecting", total=None)
                response = await websocket.recv()
                progress.update(task, completed=100)
                progress.stop()
            
            json_result = json.loads(response)
            self.console.print("[cyan]Completed:", json_result)
            return json_result


    async def async_chat(
        self, 
        message: UserMessage, 
        thread_id: str = None
    ):
        headers = {"X-Api-Key": self.api_key}
        http = "https" if self.ssl else "http"
        timeout = httpx.Timeout(60*5, connect=10)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", 
                        f"{http}://{self.api_url}/tasks/chat",
                        headers=headers,
                        json={"thread_id": thread_id, "message": message}
                    ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.strip():
                            data = json.loads(line)
                            yield data
        except (httpx.ConnectTimeout, httpx.HTTPStatusError) as e:
            print(f"HTTP or Connection Error: {str(e)}")
        except json.JSONDecodeError:
            print("Failed to decode JSON from response.")
        except Exception as e:
            print(f"An unexpected error occurred: {str(e)}")


def get_api_key() -> str:
    if os.getenv("EDEN_API_KEY"):
        return str(os.getenv("EDEN_API_KEY"))
    home_dir = os.path.expanduser("~")
    api_key_file = os.path.join(home_dir, ".eden")
    try:
        with open(api_key_file, "r") as file:
            api_key = file.read().strip()
        return str(api_key)
    except FileNotFoundError:
        return None