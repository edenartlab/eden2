#!/usr/bin/env python3

import os
import sys
import subprocess
from pathlib import Path
from dotenv import dotenv_values


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

    # Build the command with unquoted, trimmed values
    cmd_parts = ["rye", "run", "modal", "secret", "create", group_name]
    for key, value in secrets_dict.items():
        if value is not None:  # Skip None values from dotenv_values
            # Ensure value is string, trimmed, and unquoted
            value = str(value).strip().strip("'\"")
            cmd_parts.append(f"{key}={value}")
    cmd_parts.extend(["-e", env_name, "--force"])

    # Print and execute the command
    print(f"Creating {group_name}: {' '.join(cmd_parts[6:-3])}")
    subprocess.run(cmd_parts)


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: create-modal-env.py <env-name> <eve-secrets-path> <client-secrets-path>"
        )
        sys.exit(1)

    env_name = sys.argv[1]
    eve_secrets_path = Path(sys.argv[2])
    client_secrets_path = Path(sys.argv[3])

    # Create environment if it doesn't exist
    if not check_environment_exists(env_name):
        create_environment(env_name)

    # Load secrets from env files
    if client_secrets_path.exists():
        client_secrets = dotenv_values(client_secrets_path)
        create_secrets(env_name, client_secrets, "client-secrets")
    else:
        print(f"Client secrets file not found: {client_secrets_path}")

    if eve_secrets_path.exists():
        eve_secrets = dotenv_values(eve_secrets_path)
        create_secrets(env_name, eve_secrets, "eve-secrets")
    else:
        print(f"Eve secrets file not found: {eve_secrets_path}")


if __name__ == "__main__":
    main()
