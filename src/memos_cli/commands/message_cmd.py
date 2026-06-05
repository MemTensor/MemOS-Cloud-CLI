"""Execution layer for message commands."""
from __future__ import annotations

import time
from typing import Any

import typer
from rich.console import Console

from memos_cli.backend.memos_api import APIError, AuthError, get_backend
from memos_cli.config import DEFAULT_CONVERSATION_ID, load_config
from memos_cli.output import (
    format_agent_envelope,
    format_json,
    format_message_result,
    format_status_result,
)
from memos_cli.state import apply_runtime_overrides

console = Console()


def _load_backend():
    config = apply_runtime_overrides(load_config())
    return config, get_backend(config)


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, AuthError):
        console.print(f"[red]Authentication failed:[/] {exc}")
    elif isinstance(exc, APIError):
        console.print(f"[red]API error:[/] {exc}")
    else:
        console.print(f"[red]Error:[/] {exc}")
    raise typer.Exit(1)


def resolve_output_format(output_format: str | None) -> str:
    final_output = (output_format or "agent").strip().lower()
    valid = {"table", "markdown", "agent", "json"}
    if final_output not in valid:
        console.print(f"[red]Error:[/] Invalid --format: {output_format}")
        raise typer.Exit(1)
    return final_output


def cmd_message_get(
    *,
    user_id: str | None,
    conversation_id: str | None,
    limit: int,
    output_format: str | None,
) -> None:
    """Execute get message."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)

    try:
        config, backend = _load_backend()
        final_user_id = user_id or config.defaults.user_id
        if not final_user_id:
            console.print("[red]Error:[/] --user-id is required")
            raise typer.Exit(1)

        final_conversation_id = (
            conversation_id
            or config.defaults.conversation_id
            or DEFAULT_CONVERSATION_ID
        )

        result = backend.get_message(
            final_user_id,
            final_conversation_id,
            limit=limit,
        )
    except (typer.Exit, SystemExit):
        raise
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="message",
            data=result,
            duration_ms=duration_ms,
            scope={"user_id": final_user_id, "conversation_id": final_conversation_id},
            detail="simple",
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_message_result(console, result, output=final_output)


def cmd_status(
    *,
    task_id: str | None,
    output_format: str | None,
) -> None:
    """Execute get task status."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)

    if not task_id:
        console.print("[red]Error:[/] task_id is required")
        raise typer.Exit(1)

    try:
        _config, backend = _load_backend()
        result = backend.get_status(task_id)
    except (typer.Exit, SystemExit):
        raise
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="status",
            data=result,
            duration_ms=duration_ms,
            scope={"task_id": task_id},
            detail="simple",
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_status_result(console, result, output=final_output)
