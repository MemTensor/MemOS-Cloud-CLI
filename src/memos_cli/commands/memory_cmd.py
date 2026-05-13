"""Execution layer for memory commands."""
from __future__ import annotations

import sys
import time
import json
from typing import Any

import typer
from rich.console import Console

from memos_cli.backend.memos_api import APIError, AuthError, get_backend
from memos_cli.config import DEFAULT_CONVERSATION_ID, load_config
from memos_cli.output import (
    extract_memory_records_from_response,
    format_add_result,
    format_extract_result,
    format_agent_envelope,
    format_chat_result,
    format_feedback_result,
    format_json,
    format_memories_markdown,
    format_memories_text,
    format_rerank_result,
)
from memos_cli.state import apply_runtime_overrides

console = Console()
VALID_OUTPUT_FORMATS = {"table", "markdown", "agent", "json"}
VALID_DETAILS = {"simple", "detail"}
VALID_BOOL_STRINGS = {
    "true": True,
    "false": False,
    "1": True,
    "0": False,
    "yes": True,
    "no": False,
    "on": True,
    "off": False,
}


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
        "user_id": user_id or config.defaults.user_id,
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


def read_stdin_text() -> str:
    """Read stdin text when available."""
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read().strip()


def resolve_messages_json(messages_json: str | None) -> list[dict[str, Any]]:
    """Resolve required messages payload for add."""
    raw = messages_json or read_stdin_text()
    if not raw:
        console.print("[red]Error:[/] No --messages provided")
        raise typer.Exit(1)
    parsed = parse_json_option(raw, option_name="--messages")
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        console.print("[red]Error:[/] --messages must be a JSON array of objects")
        raise typer.Exit(1)
    return parsed


def resolve_message_payload(
    *,
    message_text: str | None = None,
    message_option: str | None = None,
) -> list[dict[str, Any]]:
    """Resolve a single message string into the documented API messages payload."""
    content = message_option or message_text or read_stdin_text()
    if not content:
        console.print("[red]Error:[/] No message provided")
        raise typer.Exit(1)
    return [{"role": "user", "content": content}]


def read_add_content(text: str | None, message: str | None) -> str:
    """Resolve text content from argument, option, or stdin."""
    content = text or message
    if not content:
        content = read_stdin_text()
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


def parse_bool_option(value: str | None, *, option_name: str) -> bool | None:
    """Parse a CLI boolean option from explicit true/false style strings."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in VALID_BOOL_STRINGS:
        console.print(f"[red]Error:[/] Invalid value for {option_name}: {value}")
        console.print(f"[dim]Use one of: true, false, 1, 0, yes, no, on, off[/]")
        raise typer.Exit(1)
    return VALID_BOOL_STRINGS[normalized]


def cmd_add(
    *,
    message_text: str | None,
    message_option: str | None,
    user_id: str | None,
    agent_id: str | None,
    app_id: str | None,
    conversation_id: str | None,
    tags_json: str | None,
    info_json: str | None,
    allow_public: bool | None,
    allow_knowledgebase_ids: str | None,
    async_mode: bool | None,
    output_format: str,
    detail: str,
) -> None:
    """Execute add."""
    start_time = time.time()
    messages = resolve_message_payload(message_text=message_text, message_option=message_option)
    final_output = resolve_output_format(output_format)
    final_detail = validate_detail(detail)

    try:
        config, backend = _load_backend()
        scope = resolve_scope(
            config=config,
            user_id=user_id,
            agent_id=agent_id,
            app_id=app_id,
            run_id=None,
        )
        final_conversation_id = (
            conversation_id
            or config.defaults.conversation_id
            or DEFAULT_CONVERSATION_ID
        )
        result = backend.add_memory(
            messages,
            **scope,
            conversation_id=final_conversation_id,
            tags=parse_json_option(tags_json, option_name="--tags"),
            info=parse_json_option(info_json, option_name="--info"),
            allow_public=allow_public,
            allow_knowledgebase_ids=parse_json_option(
                allow_knowledgebase_ids, option_name="--allow-knowledgebase-ids"
            ),
            async_mode=async_mode,
        )
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="add",
            data=extract_memory_records_from_response(result, detail=final_detail),
            duration_ms=duration_ms,
            scope={**scope, "conversation_id": final_conversation_id},
            detail=final_detail,
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_add_result(console, result, output="text")


def cmd_extract(
    *,
    message_text: str | None,
    message_option: str | None,
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
    messages = resolve_message_payload(message_text=message_text, message_option=message_option)
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
        final_conversation_id = (
            conversation_id
            or config.defaults.conversation_id
            or config.defaults.run_id
            or DEFAULT_CONVERSATION_ID
        )
        result = backend.extract_memory(
            messages,
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
            data=extract_memory_records_from_response(result, detail=final_detail),
            duration_ms=duration_ms,
            scope={**scope, "conversation_id": final_conversation_id},
            detail=final_detail,
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_extract_result(console, result, output="text")


def cmd_feedback(
    *,
    feedback_text: str | None,
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
    content = feedback_content or feedback_text or read_stdin_text()
    if not content:
        console.print("[red]Error:[/] No --feedback-content provided")
        raise typer.Exit(1)
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
            detail=final_detail,
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_feedback_result(console, result, output="text")


def cmd_search(
    query: str | None,
    *,
    query_option: str | None,
    user_id: str | None,
    conversation_id: str | None,
    filter_json: str | None,
    knowledgebase_ids: str | None,
    limit: int,
    include_preference: str | None,
    preference_limit: int | None,
    include_tool_memory: str | None,
    tool_memory_limit: int | None,
    include_skill: str | None,
    skill_limit: int | None,
    relativity: float | None,
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
        final_user_id = user_id or config.defaults.user_id
        final_conversation_id = (
            conversation_id
            or config.defaults.conversation_id
            or config.defaults.run_id
            or DEFAULT_CONVERSATION_ID
        )
        response = backend.search_memories(
            final_query,
            user_id=final_user_id,
            conversation_id=final_conversation_id,
            filter=parse_json_option(filter_json, option_name="--filter"),
            knowledgebase_ids=parse_json_option(knowledgebase_ids, option_name="--knowledgebase-ids"),
            limit=limit,
            include_preference=parse_bool_option(include_preference, option_name="--include-preference"),
            preference_limit=preference_limit,
            include_tool_memory=parse_bool_option(include_tool_memory, option_name="--include-tool-memory"),
            tool_memory_limit=tool_memory_limit,
            include_skill=parse_bool_option(include_skill, option_name="--include-skill-memory"),
            skill_limit=skill_limit,
            relativity=relativity,
        )
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    memories = extract_memory_records_from_response(response, detail=final_detail)[:limit]
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="search",
            data=memories,
            duration_ms=duration_ms,
            count=len(memories),
            scope={"user_id": final_user_id, "conversation_id": final_conversation_id},
            detail=final_detail,
        )
        return
    if final_output == "json":
        format_json(console, response)
    elif final_output == "markdown":
        console.print(format_memories_markdown(memories, detail=final_detail, records_preformatted=True))
    else:
        format_memories_text(console, memories, title="memories", detail=final_detail)


def cmd_rerank(
    query: str | None,
    *,
    documents: list[str] | None,
    query_option: str | None,
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
    final_detail = validate_detail(detail)

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
            detail=final_detail,
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_rerank_result(console, result, output="text")


def cmd_chat(
    query: str | None,
    *,
    query_option: str | None,
    user_id: str | None,
    agent_id: str | None,
    app_id: str | None,
    conversation_id: str | None,
    filter_json: str | None,
    knowledgebase_ids: str | None,
    memory_limit_number: int | None,
    include_preference: bool | None,
    preference_limit_number: int | None,
    relativity: float | None,
    model_name: str | None,
    system_prompt: str | None,
    stream: bool | None,
    max_tokens: int | None,
    temperature: float | None,
    top_p: float | None,
    add_message_on_answer: bool | None,
    tags_json: str | None,
    info_json: str | None,
    allow_public: bool | None,
    allow_knowledgebase_ids: str | None,
    output_format: str,
    detail: str,
) -> None:
    """Execute chat."""
    start_time = time.time()
    final_query = resolve_chat_query(query, query_option)
    final_output = resolve_output_format(output_format)
    final_detail = validate_detail(detail)

    try:
        config, backend = _load_backend()
        scope = resolve_scope(
            config=config,
            user_id=user_id,
            agent_id=agent_id,
            app_id=app_id,
            run_id=None,
        )
        final_conversation_id = (
            conversation_id
            or config.defaults.conversation_id
            or DEFAULT_CONVERSATION_ID
        )
        result = backend.chat(
            final_query,
            **scope,
            conversation_id=final_conversation_id,
            filter=parse_json_option(filter_json, option_name="--filter"),
            knowledgebase_ids=parse_json_option(knowledgebase_ids, option_name="--knowledgebase-ids"),
            memory_limit_number=memory_limit_number,
            include_preference=include_preference,
            preference_limit_number=preference_limit_number,
            relativity=relativity,
            model_name=model_name,
            system_prompt=system_prompt,
            stream=stream,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            add_message_on_answer=add_message_on_answer,
            tags=parse_json_option(tags_json, option_name="--tags"),
            info=parse_json_option(info_json, option_name="--info"),
            allow_public=allow_public,
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
            command="chat",
            data=result,
            duration_ms=duration_ms,
            scope={**scope, "conversation_id": final_conversation_id},
            detail=final_detail,
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    format_chat_result(console, result, output="text")


def cmd_get(
    *,
    user_id: str | None,
    page: int | None,
    size: int | None,
    include_preference: str | None,
    include_tool_memory: str | None,
    output_format: str,
    detail: str,
) -> None:
    """Execute get."""
    start_time = time.time()
    final_output = resolve_output_format(output_format)
    final_detail = validate_detail(detail)
    try:
        config, backend = _load_backend()
        final_user_id = user_id or config.defaults.user_id
        response = backend.get_memories(
            user_id=final_user_id,
            page=page,
            size=size,
            include_preference=parse_bool_option(include_preference, option_name="--include-preference"),
            include_tool_memory=parse_bool_option(include_tool_memory, option_name="--include-tool-memory"),
        )
    except Exception as exc:
        _handle_error(exc)

    duration_ms = int((time.time() - start_time) * 1000)
    memories = extract_memory_records_from_response(response, detail=final_detail)
    if final_output == "agent":
        format_agent_envelope(
            console,
            command="get",
            data=memories,
            duration_ms=duration_ms,
            count=len(memories),
            scope={"user_id": final_user_id},
            detail=final_detail,
        )
        return
    if final_output == "json":
        format_json(console, response)
        return
    if final_output == "markdown":
        console.print(format_memories_markdown(memories, detail=final_detail, records_preformatted=True))
        return
    format_memories_text(console, memories, title="memories", detail=final_detail, show_relevance=False)


def cmd_delete(
    memory_id: str | None,
    *,
    user_id: str | None,
    output_format: str,
    detail: str,
) -> None:
    """Execute delete."""
    final_output = resolve_output_format(output_format)
    validate_detail(detail)
    try:
        _, backend = _load_backend()
        if memory_id:
            result = backend.delete_memory([memory_id])
        elif user_id:
            result = backend.delete_memory([], user_id=user_id)
        else:
            console.print("[red]Error:[/] Provide either MEMORY_ID or --user-id")
            raise typer.Exit(1)
    except Exception as exc:
        _handle_error(exc)

    if final_output == "agent":
        format_agent_envelope(
            console,
            command="delete",
            data=result,
        )
        return
    if final_output == "json":
        format_json(console, result)
        return
    console.print("[green]✓[/] Memory deleted")


def main() -> Any:
    """Compatibility hook for direct invocation if needed."""
    return None
