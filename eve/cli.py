# eve/cli.py

import multiprocessing
import os
import random
import json
import click
import asyncio
import sys
import re

import yaml

from eve.models import ClientType

from .eden_utils import save_test_results, prepare_result
from .tool import (
    Tool,
    get_tool_dirs,
    get_tools_from_mongo,
    get_tools_from_dirs,
    save_tool_from_dir,
)
from .llm import async_prompt_thread, UserMessage, UpdateType
from eve.clients.discord.client import start as start_discord

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn


@click.group()
def cli():
    """Eve CLI"""
    pass


@cli.command()
@click.option(
    "--db",
    type=click.Choice(["STAGE", "PROD"], case_sensitive=False),
    default="STAGE",
    help="DB to save against",
)
@click.argument("tools", nargs=-1, required=False)
def update(db: str, tools: tuple):
    """Upload tools to mongo"""

    db = db.upper()

    tool_dirs = get_tool_dirs(include_inactive=True)

    if tools:
        tool_dirs = {k: v for k, v in tool_dirs.items() if k in tools}
    else:
        confirm = click.confirm(
            f"Update all {len(tool_dirs)} tools on {db}?", default=False
        )
        if not confirm:
            return

    for key, tool_dir in tool_dirs.items():
        try:
            save_tool_from_dir(tool_dir, db=db)
            click.echo(click.style(f"Updated {db}:{key}", fg="green"))
        except Exception as e:
            click.echo(click.style(f"Failed to update {db}:{key}: {e}", fg="red"))

    click.echo(click.style(f"\nUpdated {len(tool_dirs)} tools", fg="blue", bold=True))


@cli.command(context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.option(
    "--db",
    type=click.Choice(["STAGE", "PROD"], case_sensitive=False),
    default="STAGE",
    help="DB to load tools from if from mongo",
)
@click.argument("tool", required=False)
@click.pass_context
def create(ctx, tool: str, db: str):
    """Create with a tool. Args are passed as --key=value"""

    db = db.upper()

    async def async_create(tool, run_args, db):
        result = await tool.async_run(run_args, db=db)
        color = random.choice(
            [
                "black",
                "red",
                "green",
                "yellow",
                "blue",
                "magenta",
                "cyan",
                "white",
                "bright_black",
                "bright_red",
                "bright_green",
                "bright_yellow",
                "bright_blue",
                "bright_magenta",
                "bright_cyan",
                "bright_white",
            ]
        )
        if result.get("error"):
            click.echo(
                click.style(
                    f"\nFailed to test {tool.key}: {result['error']}",
                    fg="red",
                    bold=True,
                )
            )
        else:
            result = prepare_result(result, db=db)
            click.echo(
                click.style(
                    f"\nResult for {tool.key}: {json.dumps(result, indent=2)}", fg=color
                )
            )

        return result

    tool = Tool.load(tool, db=db)

    # Get args
    args = dict()
    for i in range(0, len(ctx.args), 2):
        key = ctx.args[i].lstrip("-")
        value = ctx.args[i + 1] if i + 1 < len(ctx.args) else None
        args[key] = value

    result = asyncio.run(async_create(tool, args, db))
    print(result)


@cli.command()
@click.option(
    "--yaml",
    is_flag=True,
    default=False,
    help="Whether to load tools from yaml folders (default is from mongo)",
)
@click.option(
    "--db",
    type=click.Choice(["STAGE", "PROD"], case_sensitive=False),
    default="STAGE",
    help="DB to load tools from if from mongo",
)
@click.option(
    "--api",
    is_flag=True,
    help="Run tasks against API (If not set, will run tools directly)",
)
@click.option("--parallel", is_flag=True, help="Run tests in parallel threads")
@click.option("--save", is_flag=True, default=True, help="Save test results")
@click.option("--mock", is_flag=True, default=False, help="Mock test results")
@click.argument("tools", nargs=-1, required=False)
def test(
    tools: tuple, yaml: bool, db: str, api: bool, parallel: bool, save: bool, mock: bool
):
    """Test multiple tools with their test args"""

    db = db.upper()

    async def async_test_tool(tool, api, db):
        color = random.choice(
            [
                "black",
                "red",
                "green",
                "yellow",
                "blue",
                "magenta",
                "cyan",
                "white",
                "bright_black",
                "bright_red",
                "bright_green",
                "bright_yellow",
                "bright_blue",
                "bright_magenta",
                "bright_cyan",
                "bright_white",
            ]
        )
        click.echo(click.style(f"\n\nTesting {tool.key}:", fg=color, bold=True))
        click.echo(
            click.style(f"Args: {json.dumps(tool.test_args, indent=2)}", fg=color)
        )

        if api:
            user_id = os.getenv("EDEN_TEST_USER_STAGE")
            task = await tool.async_start_task(
                user_id, tool.test_args, db=db, mock=mock
            )
            result = await tool.async_wait(task)
        else:
            result = await tool.async_run(tool.test_args, db=db, mock=mock)

        if result.get("error"):
            click.echo(
                click.style(
                    f"\nFailed to test {tool.key}: {result['error']}",
                    fg="red",
                    bold=True,
                )
            )
        else:
            result = prepare_result(result, db=db)
            click.echo(
                click.style(
                    f"\nResult for {tool.key}: {json.dumps(result, indent=2)}", fg=color
                )
            )

        return result

    async def async_run_tests(tools, api, db, parallel):
        tasks = [async_test_tool(tool, api, db) for tool in tools.values()]
        if parallel:
            results = await asyncio.gather(*tasks)
        else:
            results = [await task for task in tasks]
        return results

    if yaml:
        all_tools = get_tools_from_dirs()
    else:
        all_tools = get_tools_from_mongo(db=db)

    if tools:
        tools = {k: v for k, v in all_tools.items() if k in tools}
    else:
        tools = all_tools
        confirm = click.confirm(f"Run tests for all {len(tools)} tools?", default=False)
        if not confirm:
            return

    if "flux_trainer" in tools:
        confirm = click.confirm(
            f"Include flux_trainer test? This will take a long time.", default=False
        )
        if not confirm:
            tools.pop("flux_trainer")

    results = asyncio.run(async_run_tests(tools, api, db, parallel))

    if save and results:
        # results = prepare_result(results, db=db)
        save_test_results(tools, results)

    errors = [
        f"{tool}: {result['error']}"
        for tool, result in zip(tools.keys(), results)
        if result.get("error")
    ]
    error_list = "\n\t".join(errors)
    click.echo(
        click.style(
            f"\n\nTested {len(tools)} tools with {len(errors)} errors:\n{error_list}",
            fg="blue",
            bold=True,
        )
    )


# def interactive_chat(args):
#     import asyncio
#     asyncio.run(async_interactive_chat())


from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn


import re


def preprocess_message(message):
    metadata_pattern = r"\{.*?\}"
    attachments_pattern = r"\[.*?\]"
    # metadata_match = re.search(metadata_pattern, message)
    attachments_match = re.search(attachments_pattern, message)
    # metadata = json.loads(metadata_match.group(0)) if metadata_match else {}
    attachments = json.loads(attachments_match.group(0)) if attachments_match else []
    clean_message = re.sub(metadata_pattern, "", message)
    clean_message = re.sub(attachments_pattern, "", clean_message).strip()
    return clean_message, attachments


# @cli.command()
# @click.option('--db', type=click.Choice(['STAGE', 'PROD'], case_sensitive=False), default='STAGE', help='DB to save against')
# @click.option('--thread', type=str, default='clitest0', help='Thread name')
# @click.argument('agent', required=True, default="eve")
# def chat(db: str, thread: str, agent: str):
#     """Chat with an agent"""

#     db = db.upper()
#     user_id = os.getenv("EDEN_TEST_USER_STAGE")

#     click.echo(click.style(f"Chatting with {agent} on {db}", fg='blue', bold=True))

#     for message in prompt_thread(
#         db=db,
#         user_id=user_id,
#         thread_name=thread,
#         user_messages=UserMessage(content="can you make a picture of a fancy dog with flux_schnell? and then animate it with runway."),
#         tools=get_tools_from_mongo(db),
#         provider="anthropic"
#     ):
#         click.echo(click.style(message, fg='green', bold=True))


@cli.command()
@click.option(
    "--db",
    type=click.Choice(["STAGE", "PROD"], case_sensitive=False),
    default="STAGE",
    help="DB to save against",
)
@click.option("--thread", type=str, default="cli_test2", help="Thread name")
@click.argument("agent", required=True, default="eve")
def chat(db: str, thread: str, agent: str):
    """Chat with an agent"""

    async def async_chat(db, thread, agent):
        db = db.upper()
        user_id = os.getenv("EDEN_TEST_USER_STAGE")

        # Initial welcome message with some style
        console = Console()
        console.print("\n[bold blue]╭──────────────────────────────────╮")
        console.print("[bold blue]│          Chat with Eve           │")
        console.print("[bold blue]╰──────────────────────────────────╯\n")
        console.print("[dim]Type 'escape' to exit the chat[/dim]\n")

        while True:
            try:
                # User input with a nice prompt
                console.print("[bold yellow]You [dim]→[/dim] ", end="")
                message_input = input("\033[93m")  # ANSI code for bright yellow

                if message_input.lower() == "escape":
                    console.print("\n[dim]Goodbye! 👋[/dim]\n")
                    break

                # Add a newline for spacing
                print()

                content, attachments = preprocess_message(message_input)

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[bold cyan]"),
                    console=console,
                    transient=True,
                ) as progress:
                    task = progress.add_task("", total=None)

                    with open(os.devnull, "w") as devnull:
                        original_stdout = sys.stdout
                        sys.stdout = devnull

                        async for update in async_prompt_thread(
                            db=db,
                            user_id=user_id,
                            thread_name=thread,
                            user_messages=UserMessage(
                                content=content, attachments=attachments
                            ),
                            tools=get_tools_from_mongo(db),
                            provider="anthropic",
                        ):
                            sys.stdout = original_stdout

                            progress.update(task)
                            if update.type == UpdateType.ASSISTANT_MESSAGE:
                                console.print(
                                    "[bold green]Eve [dim]→[/dim] [green]"
                                    + update.message.content
                                )
                            elif update.type == UpdateType.TOOL_COMPLETE:
                                result = prepare_result(
                                    update.result.get("result"), db=db
                                )
                                console.print(
                                    "[bold cyan]🔧 [dim]" + update.tool_name + "[/dim]"
                                )

                                # Convert the result to a formatted string
                                formatted_result = json.dumps(result, indent=2)

                                # Make URLs clickable by wrapping them in Rich's link markup
                                formatted_result = re.sub(
                                    r'(https?://[^\s"]+)',
                                    lambda m: f"[link={m.group(1)}]{m.group(1)}[/link]",
                                    formatted_result,
                                )

                                console.print("[cyan]" + formatted_result)
                            elif update.type == UpdateType.ERROR:
                                console.print(
                                    "[bold red]❌ Error: [/bold red]"
                                    + str(update.error)
                                )

                            # Add a newline after each message for better readability
                            print()

                            sys.stdout = devnull

                        sys.stdout = original_stdout

            except KeyboardInterrupt:
                console.print("\n[dim]Chat interrupted. Goodbye! 👋[/dim]\n")
                break

    asyncio.run(async_chat(db, thread, agent))


@cli.command()
@click.option(
    "--db",
    type=click.Choice(["STAGE", "PROD"], case_sensitive=False),
    default="STAGE",
    help="DB to save against",
)
@click.option("--env", type=click.Path(exists=True), help="Path to environment file")
@click.argument(
    "agents",
    nargs=-1,
    required=True,
    type=click.Path(exists=True, resolve_path=True, path_type=str),
)
def start(db: str, env: str, agents: tuple):
    """Start one or more clients from yaml files"""

    db = db.upper()
    env_path = env or ".env"
    clients_to_start = {}

    # Load all yaml files and collect enabled clients
    for yaml_path in agents:
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
            if "clients" in config:
                for client_type, settings in config["clients"].items():
                    if settings.get("enabled", False):
                        clients_to_start[ClientType(client_type)] = yaml_path

    if not clients_to_start:
        click.echo(click.style("No enabled clients found in yaml files", fg="red"))
        return

    click.echo(click.style(f"Starting {len(clients_to_start)} clients...", fg="blue"))

    # Start each enabled client in a separate process
    processes = []
    for client_type, yaml_path in clients_to_start.items():
        try:
            if client_type == ClientType.DISCORD:
                p = multiprocessing.Process(target=start_discord, args=(env_path,))
            # elif client_type == ClientType.TELEGRAM:
            #     p = multiprocessing.Process(target=start_telegram, args=(env_path,))
            # elif client_type == ClientType.LOCAL:
            #     p = multiprocessing.Process(target=chat, args=(db,))

            p.start()
            processes.append(p)
            click.echo(click.style(f"Started {client_type.value} client", fg="green"))
        except Exception as e:
            click.echo(
                click.style(
                    f"Failed to start {client_type.value} client: {e}", fg="red"
                )
            )

    # Wait for all processes
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        click.echo(click.style("\nShutting down clients...", fg="yellow"))
        for p in processes:
            p.terminate()
            p.join()


if __name__ == "__main__":
    cli()
