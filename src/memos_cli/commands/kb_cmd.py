"""Execution layer for knowledge base commands."""
from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlparse

import typer
from rich.console import Console

from memos_cli.backend.memos_api import APIError, AuthError, get_backend
from memos_cli.commands.memory_cmd import _load_backend
from memos_cli.commands.memory_cmd import resolve_output_format, validate_detail
from memos_cli.output import (
    format_agent_envelope,
    format_kb_create_result,
    format_kb_delete_result,
    format_kb_file_add_result,
    format_kb_file_delete_result,
    format_kb_file_get_result,
)

console = Console()
SUPPORTED_KB_FILE_TYPES = {".pdf", ".docx", ".doc", ".txt", ".json", ".md", ".xml"}


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, AuthError):
        console.print(f"[red]Authentication failed:[/] {exc}")
    elif isinstance(exc, APIError):
        console.print(f"[red]API error:[/] {exc}")
    else:
        console.print(f"[red]Error:[/] {exc}")
    raise typer.Exit(1)


def _validate_kb_files(files: list[str]) -> None:
    for item in files:
        parsed = urlparse(item)
        candidate = parsed.path if parsed.scheme else item
        suffix = Path(candidate).suffix.lower()
        if suffix not in SUPPORTED_KB_FILE_TYPES:
            supported = ", ".join(sorted(ext.lstrip(".") for ext in SUPPORTED_KB_FILE_TYPES))
            console.print(
                f"[red]Error:[/] Unsupported file type for knowledge base upload: {item}\n"
                f"[dim]Supported types: {supported}[/]"
            )
            raise typer.Exit(1)


def cmd_kb_create(
    *,
    name: str,
    description: str | None,
    output_format: str | None,
    detail: str | None,
) -> None:
    """Execute knowledge base creation."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)
    validate_detail(detail)

    try:
        _, backend = _load_backend()
        result = backend.create_knowledgebase(name, description=description)
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="kb.create",
            data=result,
            duration_ms=duration_ms,
        )
        return
    format_kb_create_result(console, result, output="json" if final_output == "json" else "text")


def cmd_kb_file_add(
    *,
    knowledgebase_id: str,
    files: list[str],
    output_format: str | None,
    detail: str | None,
) -> None:
    """Execute knowledge base file add."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)
    validate_detail(detail)
    _validate_kb_files(files)

    try:
        _, backend = _load_backend()
        payload = [{"content": item} for item in files]
        result = backend.add_knowledgebase_files(knowledgebase_id, payload)
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="kb.file.add",
            data=result,
            duration_ms=duration_ms,
        )
        return
    format_kb_file_add_result(console, result, output="json" if final_output == "json" else "text")


def cmd_kb_delete(
    *,
    knowledgebase_id: str,
    output_format: str | None,
    detail: str | None,
) -> None:
    """Execute knowledge base delete."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)
    validate_detail(detail)

    try:
        _, backend = _load_backend()
        result = backend.delete_knowledgebase(knowledgebase_id)
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="kb.delete",
            data=result,
            duration_ms=duration_ms,
        )
        return
    format_kb_delete_result(console, result, output="json" if final_output == "json" else "text")


def cmd_kb_file_get(
    *,
    file_id: str,
    output_format: str | None,
    detail: str | None,
) -> None:
    """Execute knowledge base file get."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)
    validate_detail(detail)

    try:
        _, backend = _load_backend()
        result = backend.get_knowledgebase_file(file_id)
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="kb.file.get",
            data=result,
            duration_ms=duration_ms,
        )
        return
    format_kb_file_get_result(console, result, output="json" if final_output == "json" else "text")


def cmd_kb_file_delete(
    *,
    knowledgebase_id: str | None,
    file_ids: list[str],
    output_format: str | None,
    detail: str | None,
) -> None:
    """Execute knowledge base file delete."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)
    validate_detail(detail)

    try:
        _, backend = _load_backend()
        result = backend.delete_knowledgebase_files(file_ids, knowledgebase_id=knowledgebase_id)
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="kb.file.delete",
            data=result,
            duration_ms=duration_ms,
        )
        return
    format_kb_file_delete_result(console, result, output="json" if final_output == "json" else "text")
