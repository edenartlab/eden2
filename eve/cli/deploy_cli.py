import sys
import yaml
import click
import traceback
import subprocess
from pathlib import Path
from dotenv import dotenv_values

root_dir = Path(__file__).parent.parent.parent


def check_environment_exists(env_name: str) -> bool:
    result = subprocess.run(
        ["rye", "run", "modal", "environment", "list"], capture_output=True, text=True
    )
    return f"│ {env_name} " in result.stdout


def create_environment(env_name: str):
    subprocess.run(["rye", "run", "modal", "environment", "create", env_name])


def create_secrets(env_name: str, secrets_dict: dict, group_name: str):
    if not secrets_dict:
        click.echo(click.style(f"No secrets found for {group_name}", fg="yellow"))
        return

    cmd_parts = ["rye", "run", "modal", "secret", "create", group_name]
    for key, value in secrets_dict.items():
        if value is not None:
            value = str(value).strip().strip("'\"")
            cmd_parts.append(f"{key}={value}")
    cmd_parts.extend(["-e", env_name, "--force"])

    subprocess.run(cmd_parts)


def deploy_client(client_name: str, env_name: str):
    client_path = f"./eve/clients/{client_name}/modal_client.py"
    if Path(root_dir / f"eve/clients/{client_name}/modal_client.py").exists():
        subprocess.run(["rye", "run", "modal", "deploy", client_path, "-e", env_name])
    else:
        click.echo(
            click.style(
                f"Warning: Client modal file not found: {client_path}", fg="yellow"
            )
        )


def process_agent(agent_path: Path):
    with open(agent_path) as f:
        agent_config = yaml.safe_load(f)

    if not agent_config.get("deployments"):
        click.echo(click.style(f"No deployments found in {agent_path}", fg="yellow"))
        return

    agent_key = agent_path.parent.name
    click.echo(click.style(f"Processing agent: {agent_key}", fg="blue"))

    # Create environment if it doesn't exist
    if not check_environment_exists(agent_key):
        click.echo(click.style(f"Creating environment: {agent_key}", fg="green"))
        create_environment(agent_key)

    # Create secrets if .env exists
    env_file = agent_path.parent / ".env"
    if env_file.exists():
        click.echo(click.style(f"Creating secrets for: {agent_key}", fg="green"))
        client_secrets = dotenv_values(env_file)
        create_secrets(agent_key, client_secrets, "client-secrets")

    # Deploy each client
    for deployment in agent_config["deployments"]:
        click.echo(click.style(f"Deploying client: {deployment}", fg="green"))
        deploy_client(deployment, agent_key)


@click.command()
@click.argument("agent", nargs=1, required=True)
def deploy(agent: str):
    """Deploy Modal agents"""
    try:
        agents_dir = root_dir / "eve/agents"
        agent_path = agents_dir / agent / "api.yaml"
        if agent_path.exists():
            process_agent(agent_path)
        else:
            click.echo(
                click.style(f"Warning: Agent file not found: {agent_path}", fg="yellow")
            )

    except Exception as e:
        click.echo(click.style("Failed to deploy agents:", fg="red"))
        click.echo(click.style(f"Error: {str(e)}", fg="red"))
        traceback.print_exc(file=sys.stdout)


if __name__ == "__main__":
    deploy()
