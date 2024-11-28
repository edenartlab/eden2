import os
import asyncio
import httpx
from pydantic import SecretStr
from dataclasses import dataclass
from typing import Optional


@dataclass
class EdenApiUrls:
    api_url: str
    tools_api_url: str


class EdenClient:
    def __init__(
        self,
        stage=False,
        api_urls: Optional[EdenApiUrls] = None,
        api_key: Optional[SecretStr] = None,
    ):
        self.api_url = api_urls.api_url or (
            "https://staging.api.eden.art" if stage else "https://api.eden.art"
        )
        self.tools_api_url = api_urls.tools_api_url or (
            "https://edenartlab--tools-dev-fastapi-app-dev.modal.run"
            if stage
            else "https://edenartlab--tools-fastapi-app.modal.run"
        )
        self.api_key = api_key or get_api_key()

    def create(self, workflow, args):
        return asyncio.run(self.async_create(workflow, args))

    async def async_create(self, workflow, args):
        uri = f"{self.api_url}/v2/tasks/create"
        headers = {"X-Api-Key": self.api_key.get_secret_value()}
        payload = {"workflow": workflow, "args": args}

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(uri, headers=headers, json=payload)
            response.raise_for_status()
            task_id = response.json().get("task", {}).get("_id")
            async for event in self._subscribe(task_id):
                if event["status"] == "completed":
                    return event["result"]
                if event["status"] == "failed":
                    raise Exception("Error occurred while processing task")

    def chat(self, message, thread_id, agent_id):
        async def consume_chat():
            return [
                message
                async for message in self.async_chat(message, thread_id, agent_id)
            ]

        return asyncio.run(consume_chat())


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
        raise Exception(
            "\033[91mNo EDEN_API_KEY found. Please set it in your environment or run `eden login` to save it in your home directory.\033[0m"
        )
