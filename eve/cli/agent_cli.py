import click
import traceback
from ..agent import Agent, get_api_files

api_agents_order = ["eve", "abraham", "banny"]


@click.group()
def agent():
    """Agent management commands"""
    pass


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
    
    api_files = get_api_files(include_inactive=True)
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
            print("!!")
            order = agents_order.get(key, len(api_agents_order))
            print("!! 2")
            agent = Agent.from_yaml(api_file)
            print("!! 3")
            print("AGENT IS HERe")
            print(agent.tools)
            print(agent.tools.keys())
            print("SAVE 1")
            agent.save(db=db, order=order)
            print("SAVE 2")
            print("!! 4")
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
