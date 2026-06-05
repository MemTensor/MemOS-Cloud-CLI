"""Typer entrypoints for message operations."""
from __future__ import annotations

import typer

from memos_cli.commands.message_cmd import cmd_message_get, cmd_status

FORMAT_HELP = "Output format: table, markdown, agent, or json."


def message(
    user_id: str | None = typer.Option(None, "--user-id", help="User ID (required)"),
    conversation_id: str | None = typer.Option(None, "--conversation-id", help="Conversation ID"),
    limit: int = typer.Option(6, "--limit", min=1, max=50, help="Max messages to return (default 6, max 50)"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Get original conversation messages."""
    cmd_message_get(
        user_id=user_id,
        conversation_id=conversation_id,
        limit=limit,
        output_format=output_format,
    )


def status(
    task_id: str | None = typer.Argument(None, help="Async task ID (from add/feedback response)"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Get async task processing status."""
    cmd_status(
        task_id=task_id,
        output_format=output_format,
    )
