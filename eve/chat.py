import os
import sys
import json
import re

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from eve.llm import async_prompt_thread, UserMessage, UpdateType
from eve.tool import get_tools_from_mongo
from eve.eden_utils import prepare_result


def preprocess_message(message):
    metadata_pattern = r"\{.*?\}"
    attachments_pattern = r"\[.*?\]"
    attachments_match = re.search(attachments_pattern, message)
    attachments = json.loads(attachments_match.group(0)) if attachments_match else []
    clean_message = re.sub(metadata_pattern, "", message)
    clean_message = re.sub(attachments_pattern, "", clean_message).strip()
    return clean_message, attachments


async def async_chat(db, thread, agent, debug=False):
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
                    if not debug:                        
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
                            result = prepare_result(update.result.get("result"), db=db)
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
                                f"[bold red]❌ Error: [red]{str(update.error)}[/red]"
                            )

                        # Add a newline after each message for better readability
                        print()

                        if not debug:
                            sys.stdout = devnull

                    sys.stdout = original_stdout

        except KeyboardInterrupt:
            console.print("\n[dim]Chat interrupted. Goodbye! 👋[/dim]\n")
            break
