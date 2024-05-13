import os
import asyncio
import websockets
import json
from pydantic import BaseModel
from typing import Dict, Any, Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

DEFAULT_API_URL = "https://edenartlab--eden-server-fastapi-app.modal.run"

class WorkflowRequest(BaseModel):
    workflow: str
    config: Dict[str, Any]
    client_id: Optional[str] = None

class EdenClient:
    def __init__(self):
        self.url = (os.getenv("EDEN_API_URL") or DEFAULT_API_URL).lstrip("http://").lstrip("https://")
        self.api_key = os.getenv("EDEN_API_KEY")
        self.console = Console()

    def run(self, *args):
        return asyncio.run(self.run_async(*args))

    async def run_async(self, workflow, config):
        self.console.print("[bold yellow]Pending...", end="")
        
        headers = {"X-Api-Key": self.api_key}
        async with websockets.connect(
            f"wss://{self.url}/ws/tasks/run", 
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
