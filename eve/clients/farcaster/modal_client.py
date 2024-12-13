import modal
import os
from farcaster import Warpcast
from eve.clients.farcaster.client import create_app

app = modal.App(
    name="client-farcaster",
    secrets=[modal.Secret.from_name(s) for s in ["eve-secrets", "client-secrets"]],
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .env({"DB": "STAGE"})
    .apt_install("libmagic1")
    .pip_install_from_pyproject("pyproject.toml")
    .pip_install("farcaster>=0.7.11")
)


@app.function(
    image=image,
    keep_warm=1,
    concurrency_limit=1,
)
@modal.asgi_app()
def fastapi_app():
    client = Warpcast(mnemonic=os.environ.get("CLIENT_FARCASTER_MNEMONIC"))
    return create_app(client)
