import os
import re
import json
import argparse
import getpass
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .client import EdenClient, UserMessage


def preprocess_message(message):
    metadata_pattern = r'\{.*?\}'
    attachments_pattern = r'\[.*?\]'
    metadata_match = re.search(metadata_pattern, message)
    attachments_match = re.search(attachments_pattern, message)
    metadata = json.loads(metadata_match.group(0)) if metadata_match else {}
    attachments = json.loads(attachments_match.group(0)) if attachments_match else []
    clean_message = re.sub(metadata_pattern, '', message)
    clean_message = re.sub(attachments_pattern, '', clean_message).strip()
    return clean_message, metadata, attachments


def main():
    parser = argparse.ArgumentParser(description="ComfyUI Service Tool")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommands")

    install_parser = subparsers.add_parser('login', help='Cache your API key')
    install_parser.set_defaults(func=login)

    run_parser = subparsers.add_parser('chat', help='Chat with Eden')
    run_parser.set_defaults(func=chat)

    args = parser.parse_args()
    args.func(args)


def login():
    api_key = getpass.getpass("Please enter your API key: ")
    if not api_key:
        print("No API key provided. Exiting.")
        return
    home_dir = os.path.expanduser("~")
    api_key_file = os.path.join(home_dir, ".eden")
    with open(api_key_file, "w") as file:
        file.write(api_key)
    print("API key saved.")


async def async_chat():
    eden = EdenClient()
    console = Console()

    thread_id = None

    while True:
        try:
            console.print("[bold yellow]User:\t", end=' ')
            message_input = input("\033[93m\033[1m")

            if message_input.lower() == 'escape':
                break
            
            content, metadata, attachments = preprocess_message(message_input)
            message = {
                "content": content,
                "metadata": metadata,
                "attachments": attachments
            }
            
            with Progress(
                SpinnerColumn(), 
                TextColumn("[bold cyan]"), 
                console=console,
                transient=True
            ) as progress:
                task = progress.add_task("[cyan]Processing", total=None)
                async for response in eden.async_chat(
                    message=message,
                    thread_id=thread_id
                ):
                    progress.update(task)
                    thread_id = response.get("thread_id") 
                    message = response.get("message")
                    message = json.loads(message)
                    content = message.get("content") or ""
                    if message.get("tool_calls"):
                        content += f"{message['tool_calls'][0]['function']['name']}: {message['tool_calls'][0]['function']['arguments']}"
                    console.print(f"[bold green]Eden:\t{content}[/bold green]")

        except KeyboardInterrupt:
            break


def chat(args):
    import asyncio
    asyncio.run(async_chat())


if __name__ == "__main__":
    main()
