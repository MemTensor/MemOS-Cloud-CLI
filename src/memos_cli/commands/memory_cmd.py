"""Execution layer for memory commands."""
from __future__ import annotations

import sys
import time
import json
from typing import Any

import typer
from rich.console import Console

from memos_cli.backend.memos_api import APIError, AuthError, get_backend
from memos_cli.config import DEFAULT_CONVERSATION_ID, DEFAULT_USER_ID, load_config
from memos_cli.output import (
    build_memory_record,
    format_add_result,
    format_extract_result,
    format_agent_envelope,
    format_chat_result,
    format_feedback_result,
    format_json,
    format_memory_json_envelope,
    format_memories_markdown,
    format_memories_text,
    format_rerank_result,
    format_single_memory,
    strip_memory_scores,
)
from memos_cli.state import apply_runtime_overrides

console = Console()
VALID_OUTPUT_FORMATS = {"table", "markdown", "agent", "json"}
VALID_DETAILS = {"simple", "detail"}


def _load_backend():
    config = apply_runtime_overrides(load_config())
    return config, get_backend(config)


def resolve_scope(
    *,
    config,
    user_id: str | None,
    agent_id: str | None,
    app_id: str | None,
    run_id: str | None,
) -> dict[str, str | None]:
    """Resolve scope IDs from CLI flags or configured defaults."""
    return {
        "user_id": user_id or config.defaults.user_id or DEFAULT_USER_ID,
        "agent_id": agent_id or config.defaults.agent_id,
        "app_id": app_id or config.defaults.app_id,
        "run_id": run_id or config.defaults.run_id,
    }


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, AuthError):
        console.print(f"[red]Authentication failed:[/] {exc}")
    elif isinstance(exc, APIError):
        console.print(f"[red]API error:[/] {exc}")
    else:
        console.print(f"[red]Error:[/] {exc}")
    raise typer.Exit(1)


def read_add_content(text: str | None, message: str | None) -> str:
    """Resolve add content from argument, option, or stdin."""
    content = text or message
    if not content and not sys.stdin.isatty():
        content = sys.stdin.read().strip()
    if not content:
        console.print("[red]Error:[/] No text provided")
        raise typer.Exit(1)
    return content


def resolve_search_query(query: str | None, query_option: str | None) -> str:
    """Resolve search query from argument or option."""
    final_query = query_option or query
    if not final_query:
        console.print("[red]Error:[/] No query provided")
        raise typer.Exit(1)
    return final_query


def resolve_chat_query(query: str | None, query_option: str | None) -> str:
    """Resolve chat query from argument or option."""
    final_query = query_option or query
    if not final_query:
        console.print("[red]Error:[/] No query provided")
        raise typer.Exit(1)
    return final_query


def resolve_rerank_documents(
    documents: list[str] | None,
    document_options: list[str] | None,
    documents_json: str | None,
) -> list[str]:
    """Resolve rerank documents from args, repeated options, JSON, or stdin."""
    resolved: list[str] = []
    if documents:
        resolved.extend(item for item in documents if item)
    if document_options:
        resolved.extend(item for item in document_options if item)
    parsed_json = parse_json_option(documents_json, option_name="--documents-json")
    if parsed_json is not None:
        if not isinstance(parsed_json, list) or not all(isinstance(item, str) for item in parsed_json):
            console.print("[red]Error:[/] --documents-json must be a JSON array of strings")
            raise typer.Exit(1)
        resolved.extend(item for item in parsed_json if item)
    if not resolved and not sys.stdin.isatty():
        resolved.extend(line.strip() for line in sys.stdin.read().splitlines() if line.strip())
    if not resolved:
        console.print("[red]Error:[/] No documents provided")
        raise typer.Exit(1)
    return resolved


def parse_json_option(raw: str | None, *, option_name: str) -> Any | None:
    """Parse a JSON-encoded CLI option when provided."""
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        console.print(f"[red]Error:[/] Invalid JSON for {option_name}: {exc}")
        raise typer.Exit(1)


def resolve_output_format(output_format: str | None) -> str:
    """Resolve output format from the command option only."""
    final_output = (output_format or "table").strip().lower()
    if final_output not in VALID_OUTPUT_FORMATS:
        console.print(f"[red]Error:[/] Invalid --format: {output_format}")
        raise typer.Exit(1)
    return final_output


def validate_detail(detail: str | None) -> str:
    """Validate detail option."""
    final_detail = (detail or "simple").strip().lower()
    if final_detail not in VALID_DETAILS:
        console.print(f"[red]Error:[/] Invalid --detail: {detail}")
        raise typer.Exit(1)
    return final_detail


def cmd_add(
    text: str | None,
    *,
    message: str | None,
    user_id: str | None,
    agent_id: str | None,
    app_id: str | None,
    run_id: str | None,
    conversation_id: str | None,
    output_format: str,
    detail: str,
) -> None:
    """Execute add."""
    start_time = time.time()
    content = read_add_content(text, message)
    final_output = resolve_output_format(output_format)
    validate_detail(detail)

    try:
        config, backend = _load_backend()
        scope = resolve_scope(
            config=config,
            user_id=user_id,
            agent_id=agent_id,
            app_id=app_id,
            run_id=run_id,
        )
        final_conversation_id = (
            conversation_id
            or config.defaults.conversation_id
            or config.defaults.run_id
            or DEFAULT_CONVERSATION_ID
        )
        result = backend.add_memory(
            content,
            **scope,
            conversation_id=final_conversation_id,
        )
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="add",
            data=result,
            duration_ms=duration_ms,
            scope={**scope, "conversation_id": final_conversation_id},
            count=len(result.get("results", [])),
        )
        return
    format_add_result(console, result, output="json" if final_output == "json" else "text")


def cmd_extract(
    text: str | None,
    *,
    message: str | None,
    extraction_types: list[str],
    user_id: str | None,
    agent_id: str | None,
    app_id: str | None,
    run_id: str | None,
    conversation_id: str | None,
    output_format: str,
    detail: str,
) -> None:
    """Execute extract."""
    start_time = time.time()
    content = read_add_content(text, message)
    final_output = resolve_output_format(output_format)
    validate_detail(detail)

    try:
        config, backend = _load_backend()
        scope = resolve_scope(
            config=config,
            user_id=user_id,
            agent_id=agent_id,
            app_id=app_id,
            run_id=run_id,
        )
        final_conversation_id = (
            conversation_id
            or config.defaults.conversation_id
            or config.defaults.run_id
            or DEFAULT_CONVERSATION_ID
        )
        result = backend.extract_memory(
            content,
            **scope,
            conversation_id=final_conversation_id,
            extraction_types=extraction_types,
        )
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="extract",
            data=result,
            duration_ms=duration_ms,
            scope={**scope, "conversation_id": final_conversation_id},
            count=len(result.get("results", [])),
        )
        return
    format_extract_result(console, result, output="json" if final_output == "json" else "text")


def cmd_feedback(
    text: str | None,
    *,
    feedback_content: str | None,
    user_id: str | None,
    agent_id: str | None,
    app_id: str | None,
    run_id: str | None,
    conversation_id: str | None,
    allow_knowledgebase_ids: str | None,
    output_format: str,
    detail: str,
) -> None:
    """Execute feedback."""
    start_time = time.time()
    content = read_add_content(text, feedback_content)
    final_output = resolve_output_format(output_format)
    validate_detail(detail)

    try:
        config, backend = _load_backend()
        scope = resolve_scope(
            config=config,
            user_id=user_id,
            agent_id=agent_id,
            app_id=app_id,
            run_id=run_id,
        )
        final_conversation_id = (
            conversation_id
            or config.defaults.conversation_id
            or config.defaults.run_id
            or DEFAULT_CONVERSATION_ID
        )
        result = backend.add_feedback(
            content,
            **scope,
            conversation_id=final_conversation_id,
            allow_knowledgebase_ids=parse_json_option(
                allow_knowledgebase_ids, option_name="--allow-knowledgebase-ids"
            ),
        )
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="feedback",
            data=result,
            duration_ms=duration_ms,
            scope={**scope, "conversation_id": final_conversation_id},
        )
        return
    format_feedback_result(console, result, output="json" if final_output == "json" else "text")


def cmd_search(
    query: str | None,
    *,
    query_option: str | None,
    user_id: str | None,
    agent_id: str | None,
    app_id: str | None,
    run_id: str | None,
    conversation_id: str | None,
    limit: int,
    output_format: str,
    detail: str,
) -> None:
    """Execute search."""
    start_time = time.time()
    final_query = resolve_search_query(query, query_option)
    final_output = resolve_output_format(output_format)
    final_detail = validate_detail(detail)

    try:
        config, backend = _load_backend()
        scope = resolve_scope(
            config=config,
            user_id=user_id,
            agent_id=agent_id,
            app_id=app_id,
            run_id=run_id,
        )
        memories = backend.search_memories(
            final_query,
            **scope,
            conversation_id=conversation_id,
            limit=limit,
        )
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="search",
            data=memories,
            duration_ms=duration_ms,
            count=len(memories),
            scope={**scope, "conversation_id": conversation_id},
            detail=final_detail,
        )
        return
    if final_output == "json":
        format_memory_json_envelope(
            console,
            command="search",
            records=memories,
            duration_ms=duration_ms,
            detail=final_detail,
        )
    elif final_output == "markdown":
        console.print(format_memories_markdown(memories, detail=final_detail))
    else:
        format_memories_text(console, memories, title="memories", detail=final_detail)


def cmd_rerank(
    query: str | None,
    *,
    query_option: str | None,
    documents: list[str] | None,
    document_options: list[str] | None,
    documents_json: str | None,
    user_id: str | None,
    model: str | None,
    top_n: int | None,
    output_format: str,
    detail: str,
) -> None:
    """Execute rerank."""
    start_time = time.time()
    final_query = resolve_search_query(query, query_option)
    final_documents = resolve_rerank_documents(documents, document_options, documents_json)
    final_output = resolve_output_format(output_format)
    validate_detail(detail)

    try:
        _, backend = _load_backend()
        result = backend.rerank_documents(
            final_query,
            final_documents,
            user_id=user_id,
            model=model,
            top_n=top_n,
        )
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="rerank",
            data=result,
            duration_ms=duration_ms,
            count=len(result.get("results", [])),
        )
        return
    format_rerank_result(console, result, output="json" if final_output == "json" else "text")


def cmd_list(
    *,
    user_id: str | None,
    limit: int | None,
    output_format: str,
    detail: str,
) -> None:
    """Execute list."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)
    final_detail = validate_detail(detail)

    try:
        config, backend = _load_backend()
        final_user_id = user_id or config.defaults.user_id or DEFAULT_USER_ID
        memories = backend.list_memories(user_id=final_user_id, limit=limit)
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="list",
            data=memories,
            duration_ms=duration_ms,
            count=len(memories),
            scope={"user_id": final_user_id},
            detail=final_detail,
        )
        return
    if final_output == "json":
        format_memory_json_envelope(
            console,
            command="list",
            records=memories,
            duration_ms=duration_ms,
            detail=final_detail,
        )
    elif final_output == "markdown":
        console.print(format_memories_markdown(memories, detail=final_detail))
    else:
        format_memories_text(console, memories, title="memories", detail=final_detail, show_relevance=False)


def cmd_chat(
    query: str | None,
    *,
    query_option: str | None,
    user_id: str | None,
    agent_id: str | None,
    app_id: str | None,
    run_id: str | None,
    conversation_id: str | None,
    mode: str | None,
    top_k: int | None,
    pref_top_k: int | None,
    model_name_or_path: str | None,
    system_prompt: str | None,
    max_tokens: int | None,
    temperature: float | None,
    top_p: float | None,
    mem_cube_id: str | None,
    readable_cube_ids: str | None,
    writable_cube_ids: str | None,
    history: str | None,
    filter_json: str | None,
    threshold: float | None,
    moscube: bool | None,
    include_preference: bool | None,
    add_message_on_answer: bool | None,
    internet_search: bool | None,
    output_format: str,
    detail: str,
) -> None:
    """Execute chat."""
    start_time = time.time()
    final_query = resolve_chat_query(query, query_option)
    final_output = resolve_output_format(output_format)
    validate_detail(detail)

    try:
        config, backend = _load_backend()
        scope = resolve_scope(
            config=config,
            user_id=user_id,
            agent_id=agent_id,
            app_id=app_id,
            run_id=run_id,
        )
        final_conversation_id = (
            conversation_id
            or config.defaults.conversation_id
            or config.defaults.run_id
            or DEFAULT_CONVERSATION_ID
        )
        result = backend.chat(
            final_query,
            **scope,
            conversation_id=final_conversation_id,
            mode=mode,
            top_k=top_k,
            pref_top_k=pref_top_k,
            model_name_or_path=model_name_or_path,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            mem_cube_id=mem_cube_id,
            readable_cube_ids=parse_json_option(readable_cube_ids, option_name="--readable-cube-ids"),
            writable_cube_ids=parse_json_option(writable_cube_ids, option_name="--writable-cube-ids"),
            history=parse_json_option(history, option_name="--history"),
            filter=parse_json_option(filter_json, option_name="--filter"),
            threshold=threshold,
            moscube=moscube,
            include_preference=include_preference,
            add_message_on_answer=add_message_on_answer,
            internet_search=internet_search,
        )
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="chat",
            data=result,
            duration_ms=duration_ms,
            scope={**scope, "conversation_id": final_conversation_id},
        )
        return
    format_chat_result(console, result, output="json" if final_output == "json" else "text")


def cmd_get(
    memory_id: str,
    *,
    user_id: str | None,
    output_format: str,
    detail: str,
) -> None:
    """Execute get."""
    final_output = resolve_output_format(output_format)
    final_detail = validate_detail(detail)
    try:
        config, backend = _load_backend()
        final_user_id = user_id or config.defaults.user_id or DEFAULT_USER_ID
        memory = backend.get_memory(memory_id, user_id=final_user_id)
    except Exception as exc:
        _handle_error(exc)

    if final_output == "agent":
        agent_record = build_memory_record(memory, detail=final_detail)
        if final_detail == "detail":
            agent_record = strip_memory_scores(agent_record)
        format_agent_envelope(
            console,
            command="get",
            data=[agent_record],
            scope={"user_id": final_user_id},
            detail=final_detail,
            records_preformatted=True,
        )
        return
    if final_output == "json":
        json_record = build_memory_record(memory, detail=final_detail)
        if final_detail == "detail":
            json_record = strip_memory_scores(json_record)
        format_memory_json_envelope(
            console,
            command="get",
            records=json_record,
            detail=final_detail,
            records_preformatted=True,
        )
        return
    format_single_memory(console, memory, output=final_output, detail=final_detail)


def cmd_delete(
    memory_id: str,
    *,
    user_id: str | None,
    output_format: str,
    detail: str,
) -> None:
    """Execute delete."""
    final_output = resolve_output_format(output_format)
    validate_detail(detail)
    try:
        config, backend = _load_backend()
        final_user_id = user_id or config.defaults.user_id or DEFAULT_USER_ID
        result = backend.delete_memory(memory_id, user_id=final_user_id)
    except Exception as exc:
        _handle_error(exc)

    if final_output == "agent":
        format_agent_envelope(
            console,
            command="delete",
            data=result,
            scope={"user_id": final_user_id},
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    console.print(f"[green]✓[/] Memory deleted: {memory_id}")


def main() -> Any:
    """Compatibility hook for direct invocation if needed."""
    return None
