import click

from .tool_cli import tool
from .agent_cli import agent
from .chat_cli import chat
from .start_cli import start
from .upload_cli import upload
@click.group()
def cli():
    """Eve CLI"""
    pass

cli.add_command(tool)
cli.add_command(agent)
cli.add_command(chat)
cli.add_command(start)
cli.add_command(upload)