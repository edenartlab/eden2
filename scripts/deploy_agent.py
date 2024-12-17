#!/usr/bin/env python3

import subprocess
import yaml
import argparse
from pathlib import Path
from dotenv import dotenv_values

root_dir = Path(__file__).parent.parent
root_env = root_dir / ".env"

processed_environments = set()


def check_environment_exists(env_name: str) -> bool:
    result = subprocess.run(
        ["rye", "run", "modal", "environment", "list"], capture_output=True, text=True
    )
    return f"│ {env_name} " in result.stdout


def create_environment(env_name: str):
    subprocess.run(["rye", "run", "modal", "environment", "create", env_name])


def create_secrets(env_name: str, secrets_dict: dict, group_name: str):
    if not secrets_dict:
        print(f"No secrets found for {group_name}")
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
        print(f"Warning: Client modal file not found: {client_path}")


def process_agent(agent_path: Path):
    with open(agent_path) as f:
        agent_config = yaml.safe_load(f)

    if not agent_config.get("deployments"):
        print(f"No deployments found in {agent_path}")
        return

    agent_key = agent_path.parent.name

    # Create environment and secrets once per agent
    if not check_environment_exists(agent_key):
        create_environment(agent_key)

    env_file = agent_path.parent / ".env"
    if env_file.exists():
        client_secrets = dotenv_values(env_file)
        create_secrets(agent_key, client_secrets, "client-secrets")

    # Deploy each client
    for deployment in agent_config["deployments"]:
        deploy_client(deployment, agent_key)


def main():
    parser = argparse.ArgumentParser(description="Deploy Modal agents")
    parser.add_argument(
        "--agents",
        type=str,
        help="Comma-separated list of agent names to deploy (without .yaml extension)",
    )
    args = parser.parse_args()

    agents_dir = root_dir / "eve/agents"

    if args.agents:
        agent_names = [name.strip() for name in args.agents.split(",")]
        for agent_name in agent_names:
            agent_path = agents_dir / agent_name / "api.yaml"
            if agent_path.exists():
                print(f"\nProcessing agent: {agent_path.name}")
                process_agent(agent_path)
            else:
                print(f"Warning: Agent file not found: {agent_path}")
    else:
        for agent_dir in agents_dir.iterdir():
            if agent_dir.is_dir():
                agent_file = agent_dir / "api.yaml"
                if agent_file.exists():
                    print(f"\nProcessing agent: {agent_file.name}")
                    process_agent(agent_file)


if __name__ == "__main__":
    main()
