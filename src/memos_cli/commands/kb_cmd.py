"""Execution layer for knowledge base commands."""
from __future__ import annotations

import json
import time
from typing import Any

import typer
from rich.console import Console

from memos_cli.backend.memos_api import APIError, AuthError, get_backend
from memos_cli.config import load_config
from memos_cli.output import (
    format_agent_envelope,
    format_json,
    format_kb_create_result,
    format_kb_file_result,
    format_kb_remove_result,
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


def parse_json_list(raw: str | None, *, option_name: str) -> list[Any] | None:
    """Parse a JSON array from CLI option."""
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        console.print(f"[red]Error:[/] Invalid JSON for {option_name}: {exc}")
        raise typer.Exit(1)
    if not isinstance(parsed, list):
        console.print(f"[red]Error:[/] {option_name} must be a JSON array")
        raise typer.Exit(1)
    return parsed


def cmd_kb_create(
    *,
    name: str | None,
    description: str | None,
    output_format: str | None,
) -> None:
    """Execute kb create."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)

    if not name:
        console.print("[red]Error:[/] --name is required")
        raise typer.Exit(1)

    try:
        _config, backend = _load_backend()
        result = backend.kb_create(name, description)
    except (typer.Exit, SystemExit):
        raise
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="kb create",
            data=result,
            duration_ms=duration_ms,
            scope={"name": name},
            detail="simple",
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_kb_create_result(console, result, output=final_output)


def cmd_kb_remove(
    *,
    kb_id: str | None,
    output_format: str | None,
) -> None:
    """Execute kb remove."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)

    if not kb_id:
        console.print("[red]Error:[/] knowledgebase_id is required")
        raise typer.Exit(1)

    try:
        _config, backend = _load_backend()
        result = backend.kb_remove(kb_id)
    except (typer.Exit, SystemExit):
        raise
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="kb remove",
            data=result,
            duration_ms=duration_ms,
            scope={"knowledgebase_id": kb_id},
            detail="simple",
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_kb_remove_result(console, result, output=final_output)


def cmd_kb_add_file(
    *,
    kb_id: str | None,
    files_json: str | None,
    output_format: str | None,
) -> None:
    """Execute kb add-file."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)

    if not kb_id:
        console.print("[red]Error:[/] --kb-id is required")
        raise typer.Exit(1)

    files = parse_json_list(files_json, option_name="--files")
    if not files:
        console.print("[red]Error:[/] --files is required (JSON array of file objects)")
        raise typer.Exit(1)

    file_entries: list[dict[str, str]] = []
    for item in files:
        if isinstance(item, str):
            file_entries.append({"content": item})
        elif isinstance(item, dict) and "content" in item:
            file_entries.append(item)
        else:
            console.print(
                "[red]Error:[/] Each file entry must be a URL string or {\"content\": \"...\"}"
            )
            raise typer.Exit(1)

    try:
        _config, backend = _load_backend()
        result = backend.kb_add_file(kb_id, file_entries)
    except (typer.Exit, SystemExit):
        raise
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="kb add-file",
            data=result,
            duration_ms=duration_ms,
            scope={"knowledgebase_id": kb_id},
            detail="simple",
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_kb_file_result(console, result, output=final_output)


def cmd_kb_get_file(
    *,
    file_ids_json: str | None,
    output_format: str | None,
) -> None:
    """Execute kb get-file."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)

    file_ids = parse_json_list(file_ids_json, option_name="--file-ids")
    if not file_ids:
        console.print("[red]Error:[/] --file-ids is required (JSON array of file ID strings)")
        raise typer.Exit(1)

    try:
        _config, backend = _load_backend()
        result = backend.kb_get_file(file_ids)
    except (typer.Exit, SystemExit):
        raise
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="kb get-file",
            data=result,
            duration_ms=duration_ms,
            scope={"file_ids": file_ids},
            detail="simple",
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_kb_file_result(console, result, output=final_output)


def cmd_kb_list_files(
    *,
    kb_id: str | None,
    file_type: str | None,
    page: int,
    page_size: int,
    output_format: str | None,
) -> None:
    """Execute kb list-file."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)

    if not kb_id:
        console.print("[red]Error:[/] --kb-id is required")
        raise typer.Exit(1)

    if file_type and file_type not in ("document", "skill"):
        console.print("[red]Error:[/] --type must be 'document' or 'skill'")
        raise typer.Exit(1)

    try:
        _config, backend = _load_backend()
        result = backend.kb_list_files(kb_id, file_type=file_type, page=page, page_size=page_size)
    except (typer.Exit, SystemExit):
        raise
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="kb list-file",
            data=result,
            duration_ms=duration_ms,
            scope={"knowledgebase_id": kb_id, "type": file_type, "page": page, "page_size": page_size},
            detail="simple",
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_kb_file_result(console, result, output=final_output)


def cmd_kb_delete_file(
    *,
    kb_id: str | None,
    file_ids_json: str | None,
    output_format: str | None,
) -> None:
    """Execute kb delete-file."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)

    if not kb_id:
        console.print("[red]Error:[/] --kb-id is required")
        raise typer.Exit(1)

    file_ids = parse_json_list(file_ids_json, option_name="--file-ids")
    if not file_ids:
        console.print("[red]Error:[/] --file-ids is required (JSON array of file ID strings)")
        raise typer.Exit(1)

    try:
        _config, backend = _load_backend()
        result = backend.kb_delete_file(kb_id, file_ids)
    except (typer.Exit, SystemExit):
        raise
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="kb delete-file",
            data=result,
            duration_ms=duration_ms,
            scope={"knowledgebase_id": kb_id, "file_ids": file_ids},
            detail="simple",
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_kb_remove_result(console, result, output=final_output)
