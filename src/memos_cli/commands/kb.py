"""Typer entrypoints for knowledge base operations."""
from __future__ import annotations

import typer

from memos_cli.commands.kb_cmd import (
    cmd_kb_create,
    cmd_kb_delete,
    cmd_kb_file_add,
    cmd_kb_file_delete,
    cmd_kb_file_get,
)

FORMAT_HELP = "Output format: table, markdown, agent, or json."


kb_app = typer.Typer(name="kb", help="Manage knowledge bases.")
kb_file_app = typer.Typer(name="file", help="Manage knowledge base files.")


@kb_app.command("create")
def kb_create(
    name: str = typer.Argument(..., help="Knowledge base name"),
    description: str | None = typer.Option(None, "--description", "-d", help="Knowledge base description"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Create a knowledge base."""
    cmd_kb_create(name=name, description=description, output_format=output_format, detail=None)


@kb_app.command("delete")
def kb_delete(
    knowledgebase_id: str = typer.Argument(..., help="Knowledge base ID"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Delete a knowledge base."""
    cmd_kb_delete(knowledgebase_id=knowledgebase_id, output_format=output_format, detail=None)


@kb_file_app.command("add")
def kb_file_add(
    knowledgebase_id: str = typer.Argument(..., help="Knowledge base ID"),
    files: list[str] = typer.Argument(..., help="One or more file URLs"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Add file URLs to a knowledge base."""
    cmd_kb_file_add(
        knowledgebase_id=knowledgebase_id,
        files=files,
        output_format=output_format,
        detail=None,
    )


@kb_file_app.command("get")
def kb_file_get(
    file_id: str = typer.Argument(..., help="Knowledge base document ID"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Get a knowledge base document."""
    cmd_kb_file_get(file_id=file_id, output_format=output_format, detail=None)


@kb_file_app.command("delete")
def kb_file_delete(
    file_ids: list[str] = typer.Argument(..., help="One or more knowledge base file IDs"),
    knowledgebase_id: str | None = typer.Option(None, "--knowledgebase-id", help="Optional knowledge base ID"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Delete files from a knowledge base."""
    cmd_kb_file_delete(
        knowledgebase_id=knowledgebase_id,
        file_ids=file_ids,
        output_format=output_format,
        detail=None,
    )


kb_app.add_typer(kb_file_app)
