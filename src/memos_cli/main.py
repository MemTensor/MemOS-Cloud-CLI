"""Main CLI application — the entrypoint for `memos`."""
from __future__ import annotations

import typer
from rich.console import Console

from memos_cli import __version__
from memos_cli.commands.init import init_cmd
from memos_cli.commands.config_cmd import config_app
from memos_cli.commands.kb import kb_app
from memos_cli.commands.memory import add, extract, feedback, rerank, search, list, chat, get, delete
from memos_cli.state import set_runtime_options

console = Console()
err_console = Console(stderr=True)

app = typer.Typer(
    name="memos",
    help=f"◆ MemOS CLI v{__version__}\n\nThe Memory OS for AI Agents",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
    add_completion=False,
    subcommand_metavar="<command> [options]",
    options_metavar="",
)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
    api_key: str | None = typer.Option(
        None, "--api-key", help="Override API key from config."
    ),
    base_url: str | None = typer.Option(
        None, "--base-url", help="Override API base URL from config."
    ),
):
    """MemOS CLI - Universal memory interface for AI agents."""
    if version:
        console.print(f"MemOS CLI v{__version__}")
        raise typer.Exit()

    set_runtime_options(
        api_key=api_key,
        base_url=base_url,
    )

    if ctx.invoked_subcommand:
        _fire_telemetry(
            ctx.invoked_subcommand,
            extra={
                "override_api_key": bool(api_key),
                "override_base_url": bool(base_url),
            },
        )


def _fire_telemetry(command_name: str, extra: dict | None = None):
    """Fire telemetry event (non-blocking)."""
    try:
        from memos_cli.telemetry import capture_event
        props = {"command": command_name}
        if extra:
            props.update(extra)
        capture_event(f"cli.{command_name}", props)
    except Exception:
        pass


# Register subcommands
app.command("init", rich_help_panel="Setup")(init_cmd)
app.add_typer(config_app, rich_help_panel="Configuration")
app.add_typer(kb_app, rich_help_panel="Advanced")

# Memory commands (P0)
app.command(rich_help_panel="Memory Operations")(add)
app.command(rich_help_panel="Memory Operations")(extract)
app.command(rich_help_panel="Memory Operations")(feedback)
app.command(rich_help_panel="Memory Operations")(search)
app.command(rich_help_panel="Memory Operations")(list)
app.command(rich_help_panel="Memory Operations")(get)
app.command(rich_help_panel="Memory Operations")(delete)

# Advanced commands (P1)
app.command(rich_help_panel="Advanced")(rerank)
app.command(rich_help_panel="Advanced")(chat)


if __name__ == "__main__":
    app()
