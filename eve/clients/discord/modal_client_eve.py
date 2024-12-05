import modal
import os

from eve.clients.discord.client import start as discord_start


app = modal.App(
    name="eve-client-discord",
    secrets=[modal.Secret.from_name(s) for s in ["eve-stg", "eve-client-tokens"]],
)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .env(
        {
            "DB": "STAGE",
            "DISCORD_TOKEN": os.getenv("DISCORD_TOKEN"),
        }
    )
    .apt_install("libmagic1", "ffmpeg", "wget")
    .pip_install_from_pyproject("pyproject.toml")
    .pip_install("py-cord>=2.4.1")
)


@app.function(
    image=image,
    keep_warm=1,
    concurrency_limit=1,
)
@modal.asgi_app()
def modal_app() -> None:
    discord_start(env=".env", agent_key="eve")
