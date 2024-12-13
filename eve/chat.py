import os
import sys
import json
import time
import re
import logging

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from eve.llm import async_prompt_thread, UserMessage, UpdateType
from eve.thread import Thread
from eve.tool import get_tools_from_mongo
from eve.eden_utils import prepare_result, dump_json
from eve.agent import Agent
from eve.auth import get_my_eden_user

def preprocess_message(message):
    metadata_pattern = r"\{.*?\}"
    attachments_pattern = r"\[.*?\]"
    attachments_match = re.search(attachments_pattern, message)
    attachments = json.loads(attachments_match.group(0)) if attachments_match else []
    clean_message = re.sub(metadata_pattern, "", message)
    clean_message = re.sub(attachments_pattern, "", clean_message).strip()
    return clean_message, attachments


async def async_chat(db, agent_name, new_thread=True, debug=False):
    db = db.upper()

    if not debug:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("anthropic").setLevel(logging.WARNING)

    user = get_my_eden_user(db=db)
    agent = Agent.load(agent_name, db=db)

    key = f"cli_{str(agent.name)}_{str(user.id)}"
    if not new_thread:
        key += f"_{int(time.time())}"

    thread = agent.request_thread(key=key, db=db)

    console = Console()
    console.print("\n[bold blue]╭────────────────────────────────────╮")
    console.print(f"[bold blue]│{f"Chat with {agent.name}".center(36)}│")
    console.print("[bold blue]╰────────────────────────────────────╯\n")
    # console.print("[dim]Type 'escape' to exit the chat[/dim]\n")

    while True:
        try:
            console.print("[bold yellow]You [dim]→[/dim] ", end="")
            message_input = input("\033[93m")

            # if message_input.lower() == "escape":
            #     console.print("\n[dim]Goodbye! 👋[/dim]\n")
            #     break

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
                    if not debug:                        
                        sys.stdout = devnull

                    async for update in async_prompt_thread(
                        db=db,
                        user=user,
                        agent=agent,
                        thread=thread,
                        user_messages=UserMessage(
                            content=content, 
                            attachments=attachments
                        ),
                        tools=get_tools_from_mongo(db),
                        force_reply=True,
                    ):
                        sys.stdout = original_stdout

                        progress.update(task)
                        if update.type == UpdateType.ASSISTANT_MESSAGE:
                            console.print(
                                "[bold green]Eve [dim]→[/dim] [green]"
                                + update.message.content
                            )
                            print()
                        elif update.type == UpdateType.TOOL_COMPLETE:
                            result = prepare_result(update.result.get("result"), db=db)
                            console.print(
                                "[bold cyan]🔧 [dim]" + update.tool_name + "[/dim]"
                            )
                            # formatted_result = json.dumps(result, indent=2)
                            formatted_result = dump_json(result, indent=2)
                            formatted_result = re.sub(
                                r'(https?://[^\s"]+)',
                                lambda m: f"[link={m.group(1)}]{m.group(1)}[/link]",
                                formatted_result,
                            )
                            console.print("[cyan]" + formatted_result)
                            print()
                        elif update.type == UpdateType.ERROR:
                            print(update)
                            console.print(
                                f"[bold red]❌ Error: [red]{str(update.error)}[/red]"
                            )
                            print()

                        if not debug:
                            sys.stdout = devnull

                    sys.stdout = original_stdout

        except KeyboardInterrupt:
            console.print("\n[dim]Chat interrupted. Goodbye! 👋[/dim]\n")
            break
