"""Native host hook commands."""
from __future__ import annotations

import typer

from memos_cli.hooks.agents import HookConfigError, get_hook_agent_spec, hook_agent_names
from memos_cli.hooks.runner import run_stdin

hook_app = typer.Typer(help="Run native agent hook payloads.", no_args_is_help=True)


def _validate_agent(agent: str) -> None:
    try:
        get_hook_agent_spec(agent)
    except HookConfigError as exc:
        raise typer.BadParameter(str(exc), param_hint="--agent") from exc


@hook_app.command("install", hidden=True)
def install(
    agent: str = typer.Option("codex", "--agent", help=f"Target agent: {', '.join(hook_agent_names())}."),
) -> None:
    """Deprecated: install the complete integration with memos init."""
    _validate_agent(agent)
    typer.echo(f"`memos hook install` is deprecated; use `memos init --agent {agent.strip().lower()}`.", err=True)
    raise typer.Exit(2)


@hook_app.command("uninstall", hidden=True)
def uninstall(
    agent: str = typer.Option("codex", "--agent", help=f"Target agent: {', '.join(hook_agent_names())}."),
) -> None:
    """Deprecated: remove the complete integration with memos uninstall."""
    _validate_agent(agent)
    typer.echo(
        f"`memos hook uninstall` is deprecated; use `memos uninstall --agent {agent.strip().lower()} --yes`.",
        err=True,
    )
    raise typer.Exit(2)


@hook_app.command("run")
def run(
    agent: str = typer.Option("codex", "--agent", help=f"Source agent: {', '.join(hook_agent_names())}."),
    event: str | None = typer.Option(
        None,
        "--event",
        help="Host hook event name. Used when the host payload does not include hook_event_name.",
    ),
) -> None:
    """Read one native hook payload from stdin and respond with JSON."""
    _validate_agent(agent)
    run_stdin(agent=agent, event=event)
