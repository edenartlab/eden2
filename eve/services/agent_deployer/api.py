import logging
import os
import subprocess
import modal
from enum import Enum
from fastapi import Depends, FastAPI
from pydantic import BaseModel
from typing import Optional, Dict
from pathlib import Path

from eve import auth
from eve.models import ClientType


class DeployCommand(str, Enum):
    DEPLOY = "deploy"
    STOP = "stop"


class DeployRequest(BaseModel):
    agent_key: str
    platform: ClientType
    command: DeployCommand
    credentials: Optional[Dict[str, str]] = None


web_app = FastAPI()
ENV_NAME = "deployments"


def authenticate_modal_key() -> bool:
    token_id = os.getenv("MODAL_DEPLOYER_TOKEN_ID")
    token_secret = os.getenv("MODAL_DEPLOYER_TOKEN_SECRET")
    result = subprocess.run(
        [
            "modal",
            "token",
            "set",
            "--token-id",
            token_id,
            "--token-secret",
            token_secret,
        ],
        capture_output=True,
        text=True,
    )
    print(result.stdout)


def check_environment_exists(env_name: str) -> bool:
    result = subprocess.run(
        ["modal", "environment", "list"], capture_output=True, text=True
    )
    return f"│ {env_name} " in result.stdout


def create_environment(env_name: str):
    print(f"Creating environment {env_name}")
    subprocess.run(["modal", "environment", "create", env_name])


def create_modal_secrets(secrets_dict: Dict[str, str], group_name: str):
    if not secrets_dict:
        return

    cmd_parts = ["modal", "secret", "create", group_name]
    for key, value in secrets_dict.items():
        if value is not None:
            value = str(value).strip().strip("'\"")
            cmd_parts.append(f"{key}={value}")
    cmd_parts.extend(["-e", ENV_NAME, "--force"])

    subprocess.run(cmd_parts)


def deploy_client(client_name: str):
    client_path = f"./eve/clients/{client_name}/modal_client.py"
    if Path(client_path).exists():
        subprocess.run(["modal", "deploy", client_path, "-e", ENV_NAME])
    else:
        raise Exception(f"Client modal file not found: {client_path}")


def stop_client(client_name: str):
    subprocess.run(["modal", "app", "stop", f"client-{client_name}", "-e", ENV_NAME])


@web_app.post("/")
async def deploy_handler(request: DeployRequest):
    try:
        if request.credentials:
            create_modal_secrets(
                request.credentials,
                f"{request.agent_key}-client-secrets",
            )

        # if request.command == DeployCommand.DEPLOY:
        #     deploy_client(request.platform.value, request.agent_key)
        #     return {
        #         "status": "success",
        #         "message": f"Deployed {request.platform.value} client",
        #     }
        # else:
        #     stop_client(request.platform.value, request.agent_key)
        #     return {
        #         "status": "success",
        #         "message": f"Stopped {request.platform.value} client",
        #     }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# Modal app setup
app = modal.App(
    name="agent-deployer-api", secrets=[modal.Secret.from_name("eve-secrets")]
)

image = modal.Image.debian_slim(python_version="3.11").pip_install_from_pyproject(
    "pyproject.toml"
)


@app.function(
    image=image,
    keep_warm=1,
    concurrency_limit=10,
    timeout=300,
)
@modal.asgi_app()
def fastapi_app():
    authenticate_modal_key()
    if not check_environment_exists(ENV_NAME):
        create_environment(ENV_NAME)
    return web_app
