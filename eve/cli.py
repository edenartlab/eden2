# eve/cli.py

import os
import random
import json
import click
import asyncio

from .tool import get_tool_dirs, get_tools_from_mongo, get_tools_from_dirs, save_tool_from_dir
from .eden_utils import save_test_results


@click.group()
def cli():
    """Eve CLI"""
    pass




@cli.command()
@click.option('--env', type=click.Choice(['STAGE', 'PROD']), default='STAGE', help='DB to save against')
@click.argument('agent', required=True)
def chat(env: str, agent: str):
    """Update tools in mongo"""
    
    click.echo(click.style(f"Chatting with {agent} on {env}", fg='blue', bold=True))





@cli.command()
@click.option('--env', type=click.Choice(['STAGE', 'PROD']), default='STAGE', help='DB to save against')
@click.argument('tools', nargs=-1, required=False)
def update(env: str, tools: tuple):
    """Update tools in mongo"""
    
    tool_dirs = get_tool_dirs()
    
    if tools:
        tool_dirs = {k: v for k, v in tool_dirs.items() if k in tools}
    else:
        confirm = click.confirm(f"Update all {len(tool_dirs)} tools on {env}?", default=False)
        if not confirm:
            return

    for key, tool_dir in tool_dirs.items():
        try:
            save_tool_from_dir(tool_dir, env=env)
            click.echo(click.style(f"Updated {env}:{key}", fg='green'))
        except Exception as e:
            click.echo(click.style(f"Failed to update {env}:{key}: {e}", fg='red'))

    click.echo(click.style(f"\nUpdated {len(tool_dirs)} tools", fg='blue', bold=True))


@cli.command()
@click.option('--from_dirs', default=True, help='Whether to load tools from folders (default is from mongo)')
@click.option('--env', type=click.Choice(['STAGE', 'PROD']), default='STAGE', help='DB to load tools from if from mongo')
@click.option('--api', is_flag=True, help='Run tasks against API (If not set, will run tools directly)')
@click.option('--parallel', is_flag=True, default=True, help='Run tests in parallel threads')
@click.option('--save', is_flag=True, default=True, help='Save test results')
@click.option('--mock', is_flag=True, default=False, help='Mock test results')
@click.argument('tools', nargs=-1, required=False)
def test(
    tools: tuple,
    from_dirs: bool, 
    env: str, 
    api: bool, 
    parallel: bool, 
    save: bool,
    mock: bool
):
    """Run tools with test args"""

    async def async_test_tool(tool, api, env):
        color = random.choice(["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white", "bright_black", "bright_red", "bright_green", "bright_yellow", "bright_blue", "bright_magenta", "bright_cyan", "bright_white"])
        click.echo(click.style(f"\n\nTesting {tool.key}:", fg=color, bold=True))
        click.echo(click.style(f"Args: {json.dumps(tool.test_args, indent=2)}", fg=color))

        if api:
            user_id = os.getenv("EDEN_TEST_USER_STAGE")
            task = await tool.async_start_task(user_id, tool.test_args, env=env, mock=mock)
            result = await tool.async_wait(task)
        else:
            result = await tool.async_run(tool.test_args, env=env, mock=mock)
        
        if "error" in result:
            click.echo(click.style(f"Failed to test {tool.key}: {result['error']}", fg='red', bold=True))
        else:
            click.echo(click.style(f"Result: {json.dumps(result, indent=2)}", fg=color))

        return result

    async def async_run_tests(tools, api, env, parallel):
        tasks = [async_test_tool(tool, api, env) for tool in tools.values()]
        if parallel:
            results = await asyncio.gather(*tasks)
        else:
            results = [await task for task in tasks]
        return results

    if from_dirs:
        all_tools = get_tools_from_dirs()
    else:
        all_tools = get_tools_from_mongo(env=env)

    if tools:
        tools = {k: v for k, v in all_tools.items() if k in tools}
    else:
        tools = all_tools
        confirm = click.confirm(f"Run tests for all {len(tools)} tools?", default=False)
        if not confirm:
            return

    results = asyncio.run(async_run_tests(tools, api, env, parallel))
    if save and results:
        save_test_results(tools, results)


    errors = [result for result in results if "error" in result]
    click.echo(click.style(f"\n\nTested {len(tools)} tools with {len(errors)} errors: {', '.join(errors)}", fg='blue', bold=True))


if __name__ == '__main__':
    cli()
