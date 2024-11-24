# eve/cli.py

import os
import random
import json
import click
import asyncio

from .tool import Tool, get_tool_dirs, get_tools_from_mongo, get_tools_from_dirs, save_tool_from_dir
from .eden_utils import save_test_results, prepare_result


@click.group()
def cli():
    """Eve CLI"""
    pass


@cli.command()
@click.option('--db', type=click.Choice(['STAGE', 'PROD'], case_sensitive=False), default='STAGE', help='DB to save against')
@click.argument('tools', nargs=-1, required=False)
def update(db: str, tools: tuple):
    """Upload tools to mongo"""

    db = db.upper()
    
    tool_dirs = get_tool_dirs(include_inactive=True)
    
    if tools:
        tool_dirs = {k: v for k, v in tool_dirs.items() if k in tools}
    else:
        confirm = click.confirm(f"Update all {len(tool_dirs)} tools on {db}?", default=False)
        if not confirm:
            return

    for key, tool_dir in tool_dirs.items():
        try:
            save_tool_from_dir(tool_dir, db=db)
            click.echo(click.style(f"Updated {db}:{key}", fg='green'))
        except Exception as e:
            click.echo(click.style(f"Failed to update {db}:{key}: {e}", fg='red'))

    click.echo(click.style(f"\nUpdated {len(tool_dirs)} tools", fg='blue', bold=True))


@cli.command(context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@click.option('--db', type=click.Choice(['STAGE', 'PROD'], case_sensitive=False), default='STAGE', help='DB to load tools from if from mongo')
@click.argument('tool', required=False)
@click.pass_context
def create(ctx, tool: str, db: str):
    """Create with a tool. Args are passed as --key=value"""

    db = db.upper()

    async def async_create(tool, run_args, db):
        result = await tool.async_run(run_args, db=db)
        
        color = random.choice(["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white", "bright_black", "bright_red", "bright_green", "bright_yellow", "bright_blue", "bright_magenta", "bright_cyan", "bright_white"])
        if "error" in result:
            click.echo(click.style(f"\nFailed to test {tool.key}: {result['error']}", fg='red', bold=True))
        else:
            result = prepare_result(result, db=db)
            click.echo(click.style(f"\nResult for {tool.key}: {json.dumps(result, indent=2)}", fg=color))

        return result

    tool = Tool.load(tool, db=db)
    
    # Get args
    args = dict()
    for i in range(0, len(ctx.args), 2):
        key = ctx.args[i].lstrip('-')
        value = ctx.args[i + 1] if i + 1 < len(ctx.args) else None
        args[key] = value
    
    result = asyncio.run(async_create(tool, args, db))
    print(result)


@cli.command()
@click.option('--yaml', is_flag=True, default=False, help='Whether to load tools from yaml folders (default is from mongo)')
@click.option('--db', type=click.Choice(['STAGE', 'PROD'], case_sensitive=False), default='STAGE', help='DB to load tools from if from mongo')
@click.option('--api', is_flag=True, help='Run tasks against API (If not set, will run tools directly)')
@click.option('--parallel', is_flag=True, help='Run tests in parallel threads')
@click.option('--save', is_flag=True, default=True, help='Save test results')
@click.option('--mock', is_flag=True, default=False, help='Mock test results')
@click.argument('tools', nargs=-1, required=False)
def test(
    tools: tuple,
    yaml: bool, 
    db: str, 
    api: bool, 
    parallel: bool, 
    save: bool,
    mock: bool
):
    """Test multiple tools with their test args"""

    db = db.upper()

    async def async_test_tool(tool, api, db):
        color = random.choice(["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white", "bright_black", "bright_red", "bright_green", "bright_yellow", "bright_blue", "bright_magenta", "bright_cyan", "bright_white"])
        click.echo(click.style(f"\n\nTesting {tool.key}:", fg=color, bold=True))
        click.echo(click.style(f"Args: {json.dumps(tool.test_args, indent=2)}", fg=color))

        if api:
            user_id = os.getenv("EDEN_TEST_USER_STAGE")
            task = await tool.async_start_task(user_id, tool.test_args, db=db, mock=mock)
            result = await tool.async_wait(task)
        else:
            result = await tool.async_run(tool.test_args, db=db, mock=mock)
        
        if "error" in result:
            click.echo(click.style(f"\nFailed to test {tool.key}: {result['error']}", fg='red', bold=True))
        else:
            result = prepare_result(result, db=db)
            click.echo(click.style(f"\nResult for {tool.key}: {json.dumps(result, indent=2)}", fg=color))

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
        confirm = click.confirm(f"Include flux_trainer test? This will take a long time.", default=False)
        if not confirm:
            tools.pop("flux_trainer")

    results = asyncio.run(
        async_run_tests(tools, api, db, parallel)
    )
    
    if save and results:
        save_test_results(tools, results)

    errors = [f"{tool}: {result['error']}" for tool, result in zip(tools.keys(), results) if "error" in result]
    error_list = "\n\t".join(errors)
    click.echo(click.style(f"\n\nTested {len(tools)} tools with {len(errors)} errors:\n{error_list}", fg='blue', bold=True))


@cli.command()
@click.option('--db', type=click.Choice(['STAGE', 'PROD'], case_sensitive=False), default='STAGE', help='DB to save against')
@click.argument('agent', required=True, default="eve")
def chat(db: str, agent: str):
    """Chat with an agent"""

    db = db.upper()
    
    click.echo(click.style(f"Chatting with {agent} on {db}", fg='blue', bold=True))
    click.echo(click.style(f"Note: this is not available yet.", fg='red', bold=True))


if __name__ == '__main__':
    cli()
