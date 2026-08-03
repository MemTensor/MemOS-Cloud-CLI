"""Native host hook commands."""
from __future__ import annotations

import typer

from memos_cli.hooks.runner import run_stdin

hook_app = typer.Typer(help="Run native agent hook payloads.", no_args_is_help=True)


def _validate_agent(agent: str) -> None:
    if agent.strip().lower() != "codex":
        raise typer.BadParameter("Native Hook is currently supported only for codex", param_hint="--agent")


@hook_app.command("install", hidden=True)
def install(
    agent: str = typer.Option("codex", "--agent", help="Target agent (currently: codex)."),
) -> None:
    """Deprecated: install the complete Codex integration with memos init."""
    _validate_agent(agent)
    typer.echo("`memos hook install` is deprecated; use `memos init --agent codex`.", err=True)
    raise typer.Exit(2)


@hook_app.command("uninstall", hidden=True)
def uninstall(
    agent: str = typer.Option("codex", "--agent", help="Target agent (currently: codex)."),
) -> None:
    """Deprecated: remove the complete integration with memos uninstall."""
    _validate_agent(agent)
    typer.echo(
        "`memos hook uninstall` is deprecated; use `memos uninstall --agent codex --yes`.",
        err=True,
    )
    raise typer.Exit(2)


@hook_app.command("run")
def run(
    agent: str = typer.Option("codex", "--agent", help="Source agent (currently: codex)."),
) -> None:
    """Read one Codex hook payload from stdin and respond with JSON."""
    _validate_agent(agent)
    run_stdin()
