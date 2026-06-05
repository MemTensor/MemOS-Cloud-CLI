"""Typer entrypoints for knowledge base operations."""
from __future__ import annotations

import typer

from memos_cli.commands.kb_cmd import (
    cmd_kb_add_file,
    cmd_kb_create,
    cmd_kb_delete_file,
    cmd_kb_get_file,
    cmd_kb_list_files,
    cmd_kb_remove,
)

FORMAT_HELP = "Output format: table, markdown, agent, or json."

kb_app = typer.Typer(
    name="kb",
    help="Knowledge base management.",
    no_args_is_help=True,
)


@kb_app.command("create")
def kb_create(
    name: str = typer.Option(..., "--name", help="Knowledge base name (required)"),
    description: str | None = typer.Option(None, "--description", help="Knowledge base description"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Create a new knowledge base."""
    cmd_kb_create(name=name, description=description, output_format=output_format)


@kb_app.command("remove")
def kb_remove(
    kb_id: str = typer.Argument(..., help="Knowledge base ID to remove"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Remove (delete) a knowledge base."""
    cmd_kb_remove(kb_id=kb_id, output_format=output_format)


@kb_app.command("add-file")
def kb_add_file(
    kb_id: str = typer.Option(..., "--kb-id", help="Target knowledge base ID"),
    files: str = typer.Option(
        ...,
        "--files",
        help='JSON array of file entries: ["https://..."] or [{"content":"..."}]',
    ),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Upload documents to a knowledge base."""
    cmd_kb_add_file(kb_id=kb_id, files_json=files, output_format=output_format)


@kb_app.command("get-file")
def kb_get_file(
    file_ids: str = typer.Option(
        ..., "--file-ids", help='JSON array of file IDs: ["file_id_1", ...]'
    ),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Get knowledge base file details and processing status."""
    cmd_kb_get_file(file_ids_json=file_ids, output_format=output_format)


@kb_app.command("list-file")
def kb_list_file(
    kb_id: str = typer.Option(..., "--kb-id", help="Knowledge base ID"),
    file_type: str | None = typer.Option(None, "--type", help="Filter by type: document or skill"),
    page: int = typer.Option(1, "--page", help="Page number (default: 1)"),
    page_size: int = typer.Option(20, "--page-size", help="Items per page (default: 20)"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """List files in a knowledge base with pagination."""
    cmd_kb_list_files(kb_id=kb_id, file_type=file_type, page=page, page_size=page_size, output_format=output_format)


@kb_app.command("delete-file")
def kb_delete_file(
    kb_id: str = typer.Option(..., "--kb-id", help="Knowledge base ID"),
    file_ids: str = typer.Option(
        ..., "--file-ids", help='JSON array of file IDs to delete: ["file_id_1", ...]'
    ),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Delete files from a knowledge base."""
    cmd_kb_delete_file(kb_id=kb_id, file_ids_json=file_ids, output_format=output_format)
