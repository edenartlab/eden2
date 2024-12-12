# eve/cli.py

import multiprocessing
from pathlib import Path
import traceback
import os
import random
import json
import click
import asyncio
import time

import yaml
from dotenv import load_dotenv

from eve.chat import async_chat
from eve.models import ClientType

from .eden_utils import save_test_results, prepare_result, dump_json, CLICK_COLORS
from eve import tool as eve_tool
from eve import agent as eve_agent
from eve.tool import Tool, get_tools_from_mongo, get_tools_from_api_files
from eve.agent import Agent
from eve.clients.discord.client import start as start_discord
from eve.auth import get_eden_user_id

api_tools_order = [
    "txt2img",
    "flux_dev",
    "flux_schnell",
    "layer_diffusion",
    "remix_flux_schnell",
    "remix",
    "inpaint",
    "flux_inpainting",
    "outpaint",
    "face_styler",
    "upscaler",
    "background_removal",
    "style_transfer",
    "storydiffusion",
    "xhibit_vton",
    "xhibit_remix",
    "beeple_ai",
    "txt2img_test",
    "sd3_txt2img",
    "HelloMeme_image",
    "HelloMeme_video",
    "flux_redux",
    "mars-id",
    "background_removal_video",
    "animate_3D",
    "style_mixing",
    "txt2vid",
    "vid2vid_sdxl",
    "img2vid",
    "video_upscaler",
    "frame_interpolation",
    "reel",
    "story",
    "texture_flow",
    "runway",
    "animate_3D_new",
    "mochi_preview",
    "lora_trainer",
    "flux_trainer",
    "news",
    "moodmix",
    "stable_audio",
    "musicgen",
    "legacy/create",
]
api_agents_order = ["eve"]


@click.group()
def cli():
    """Eve CLI"""
    pass


@cli.group()
def tool():
    """Tool management commands"""
    pass


@cli.group()
def agent():
    """Agent management commands"""
    pass


@tool.command()
@click.option(
    "--db",
    type=click.Choice(["STAGE", "PROD"], case_sensitive=False),
    default="STAGE",
    help="DB to save against",
)
@click.argument("names", nargs=-1, required=False)
def update(db: str, names: tuple):
    """Upload tools to mongo"""
    db = db.upper()
    api_files = eve_tool.get_api_files(include_inactive=True)
    tools_order = {tool: index for index, tool in enumerate(api_tools_order)}

    if names:
        api_files = {k: v for k, v in api_files.items() if k in names}
    else:
        confirm = click.confirm(
            f"Update all {len(api_files)} tools on {db}?", default=False
        )
        if not confirm:
            return

    updated = 0
    for key, api_file in api_files.items():
        try:
            order = tools_order.get(key, len(api_tools_order))
            tool = Tool.from_yaml(api_file)
            tool.save(db=db, order=order)
            click.echo(
                click.style(f"Updated tool {db}:{key} (order={order})", fg="green")
            )
            updated += 1
        except Exception as e:
            traceback.print_exc()
            click.echo(click.style(f"Failed to update tool {db}:{key}: {e}", fg="red"))

    click.echo(
        click.style(
            f"\nUpdated {updated} of {len(api_files)} tools", fg="blue", bold=True
        )
    )
    click.echo(
        click.style(
            f"\nUpdated {updated} of {len(api_files)} tools", fg="blue", bold=True
        )
    )


@agent.command()
@click.option(
    "--db",
    type=click.Choice(["STAGE", "PROD"], case_sensitive=False),
    default="STAGE",
    help="DB to save against",
)
@click.argument("names", nargs=-1, required=False)
def update(db: str, names: tuple):
    """Upload agents to mongo"""
    db = db.upper()
    api_files = eve_agent.get_api_files(include_inactive=True)
    agents_order = {agent: index for index, agent in enumerate(api_agents_order)}

    if names:
        api_files = {k: v for k, v in api_files.items() if k in names}
    else:
        confirm = click.confirm(
            f"Update all {len(api_files)} agents on {db}?", default=False
        )
        if not confirm:
            return

    updated = 0
    for key, api_file in api_files.items():
        try:
            order = agents_order.get(key, len(api_agents_order))
            agent = Agent.from_yaml(api_file)
            agent.save(db=db, order=order)
            click.echo(
                click.style(f"Updated agent {db}:{key} (order={order})", fg="green")
            )
            updated += 1
        except Exception as e:
            traceback.print_exc()
            click.echo(click.style(f"Failed to update agent {db}:{key}: {e}", fg="red"))

    click.echo(
        click.style(
            f"\nUpdated {updated} of {len(api_files)} agents", fg="blue", bold=True
        )
    )


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

    tool = Tool.load(key=tool, db=db)

    # Get args
    args = dict()
    for i in range(0, len(ctx.args), 2):
        key = ctx.args[i].lstrip("-")
        value = ctx.args[i + 1] if i + 1 < len(ctx.args) else None
        args[key] = value

    result = tool.run(args, db=db)
    color = random.choice(CLICK_COLORS)
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
            click.style(f"\nResult for {tool.key}: {dump_json(result)}", fg=color)
        )

    print(result)
    return result


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
        color = random.choice(CLICK_COLORS)
        click.echo(click.style(f"\n\nTesting {tool.key}:", fg=color, bold=True))
        click.echo(click.style(f"Args: {dump_json(tool.test_args)}", fg=color))

        if api:
            user_id = get_eden_user_id(db=db)
            task = await tool.async_start_task(
                user_id, user_id, tool.test_args, db=db, mock=mock
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
                click.style(f"\nResult for {tool.key}: {dump_json(result)}", fg=color)
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
        all_tools = get_tools_from_api_files(tools=tools)
    else:
        all_tools = get_tools_from_mongo(db=db, tools=tools)

    if not tools:
        confirm = click.confirm(
            f"Run tests for all {len(all_tools)} tools?", default=False
        )
        if not confirm:
            return

    if "flux_trainer" in all_tools:
        confirm = click.confirm(
            "Include flux_trainer test? This will take a long time.", default=False
        )
        if not confirm:
            all_tools.pop("flux_trainer")

    results = asyncio.run(async_run_tests(all_tools, api, db, parallel))

    if save and results:
        # results = prepare_result(results, db=db)
        save_test_results(all_tools, results)

    errors = [
        f"{tool}: {result['error']}"
        for tool, result in zip(all_tools.keys(), results)
        if result.get("error")
    ]
    error_list = "\n\t".join(errors)
    click.echo(
        click.style(
            f"\n\nTested {len(all_tools)} tools with {len(errors)} errors:\n{error_list}",
            fg="blue",
            bold=True,
        )
    )


@cli.command()
@click.option(
    "--db",
    type=click.Choice(["STAGE", "PROD"], case_sensitive=False),
    default="STAGE",
    help="DB to save against",
)
@click.option("--thread", type=str, help="Thread id")
@click.option("--debug", is_flag=True, default=False, help="Debug mode")
@click.argument("agent", required=True, default="eve")
def chat(db: str, thread: str, agent: str, debug: bool):
    """Chat with an agent"""
    asyncio.run(async_chat(db, agent, thread, debug))


def start_local_chat(db: str, agent_dir: str):
    """Wrapper function for chat that can be pickled"""
    load_dotenv(agent_dir / ".env")
    # Get the agent name from the yaml file
    with open(agent_dir / "api.yaml") as f:  # or pass this path as parameter
        config = yaml.safe_load(f)
        agent = config.get("name", "eve").lower()

    thread = f"local_client_{int(time.time())}"  # unique thread name
    asyncio.run(async_chat(db, agent, thread))


@cli.command()
@click.argument("agent", nargs=1, required=True)
@click.option(
    "--db",
    type=click.Choice(["STAGE", "PROD"], case_sensitive=False),
    default="STAGE",
    help="DB to save against",
)
@click.option(
    "--env",
    type=click.Path(exists=True, resolve_path=True),
    help="Path to environment file",
)
def start(agent: str, db: str, env: str):
    """Start one or more clients from yaml files"""
    agent_dir = Path(__file__).parent / "agents" / agent
    env_path = agent_dir / ".env"
    yaml_path = agent_dir / "api.yaml"

    db = db.upper()
    env_path = env or env_path
    clients_to_start = {}

    # Load all yaml files and collect enabled clients
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

    # Start discord and telegram first, local client last
    processes = []
    for client_type, yaml_path in clients_to_start.items():
        if client_type != ClientType.LOCAL:
            try:
                if client_type == ClientType.DISCORD:
                    p = multiprocessing.Process(
                        target=start_discord,
                        args=(env_path, agent)
                    )
                # elif client_type == ClientType.TELEGRAM:
                #     p = multiprocessing.Process(target=start_telegram, args=(env_path,))

                p.start()
                processes.append(p)
                click.echo(
                    click.style(f"Started {client_type.value} client", fg="green")
                )
            except Exception as e:
                click.echo(
                    click.style(
                        f"Failed to start {client_type.value} client: {e}", fg="red"
                    )
                )

    # Start local client last to maintain terminal focus
    if ClientType.LOCAL in clients_to_start:
        try:
            click.echo(click.style("Starting local client...", fg="blue"))
            start_local_chat(db, agent_dir)
        except Exception as e:
            click.echo(click.style(f"Failed to start local client: {e}", fg="red"))

    # Wait for other processes
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
