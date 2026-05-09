"""Typer entrypoints for memory operations."""
from __future__ import annotations

from typing import List
import typer

from memos_cli.commands.memory_cmd import (
    cmd_add,
    cmd_chat,
    cmd_delete,
    cmd_extract,
    cmd_get,
    cmd_list,
    cmd_rerank,
    cmd_search,
)


def add(
    text: str | None = typer.Argument(None, help="Text content to add as memory."),
    message: str | None = typer.Option(None, "--message", "-m", help="Text content to add."),
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    agent_id: str | None = typer.Option(None, "--agent-id", help="Agent ID"),
    app_id: str | None = typer.Option(None, "--app-id", help="App ID"),
    run_id: str | None = typer.Option(None, "--run-id", help="Run ID"),
    conversation_id: str | None = typer.Option(None, "--conversation-id", help="Conversation ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Add a new memory."""
    cmd_add(
        text,
        message=message,
        user_id=user_id,
        agent_id=agent_id,
        app_id=app_id,
        run_id=run_id,
        conversation_id=conversation_id,
        json_output=json_output,
    )


def extract(
    text: str | None = typer.Argument(None, help="Text content to extract memories from."),
    message: str | None = typer.Option(None, "--message", "-m", help="Text content to extract from."),
    extraction_types: List[str] = typer.Option(
        ["memory", "preference"],
        "--type",
        help="Extraction type(s), e.g. memory, preference",
    ),
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    agent_id: str | None = typer.Option(None, "--agent-id", help="Agent ID"),
    app_id: str | None = typer.Option(None, "--app-id", help="App ID"),
    run_id: str | None = typer.Option(None, "--run-id", help="Run ID"),
    conversation_id: str | None = typer.Option(None, "--conversation-id", help="Conversation ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Extract memory candidates without storing them."""
    cmd_extract(
        text,
        message=message,
        extraction_types=extraction_types,
        user_id=user_id,
        agent_id=agent_id,
        app_id=app_id,
        run_id=run_id,
        conversation_id=conversation_id,
        json_output=json_output,
    )


def search(
    query: str | None = typer.Argument(None, help="Search query"),
    query_option: str | None = typer.Option(None, "--query", "-q", help="Search query"),
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    agent_id: str | None = typer.Option(None, "--agent-id", help="Agent ID"),
    app_id: str | None = typer.Option(None, "--app-id", help="App ID"),
    run_id: str | None = typer.Option(None, "--run-id", help="Run ID"),
    conversation_id: str | None = typer.Option(None, "--conversation-id", help="Conversation ID"),
    limit: int = typer.Option(10, "--limit", "-n", min=1, help="Number of results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Search memories."""
    cmd_search(
        query,
        query_option=query_option,
        user_id=user_id,
        agent_id=agent_id,
        app_id=app_id,
        run_id=run_id,
        conversation_id=conversation_id,
        limit=limit,
        json_output=json_output,
    )


def rerank(
    query: str | None = typer.Argument(None, help="Query used to rerank the candidate documents"),
    documents: List[str] | None = typer.Argument(None, help="Candidate documents to rerank"),
    query_option: str | None = typer.Option(None, "--query", "-q", help="Query used to rerank the candidate documents"),
    document_option: List[str] | None = typer.Option(None, "--document", "-d", help="Candidate document, repeatable"),
    documents_json: str | None = typer.Option(None, "--documents-json", help="JSON array of candidate documents"),
    model: str | None = typer.Option(None, "--model", help="Reranker model name"),
    top_n: int | None = typer.Option(None, "--top-n", min=1, help="Return top N results only"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Rerank candidate documents for a query."""
    cmd_rerank(
        query,
        query_option=query_option,
        documents=documents,
        document_options=document_option,
        documents_json=documents_json,
        model=model,
        top_n=top_n,
        json_output=json_output,
    )


def list(
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    limit: int | None = typer.Option(None, "--limit", "-n", min=1, help="Maximum memories to return"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List memories."""
    cmd_list(user_id=user_id, limit=limit, json_output=json_output)


def chat(
    query: str | None = typer.Argument(None, help="Chat query"),
    query_option: str | None = typer.Option(None, "--query", "-q", help="Chat query"),
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    agent_id: str | None = typer.Option(None, "--agent-id", help="Agent ID"),
    app_id: str | None = typer.Option(None, "--app-id", help="App ID"),
    run_id: str | None = typer.Option(None, "--run-id", help="Run ID"),
    conversation_id: str | None = typer.Option(None, "--conversation-id", help="Conversation ID"),
    mode: str | None = typer.Option(None, "--mode", help="Search mode: fast, fine, or mixture"),
    top_k: int | None = typer.Option(None, "--top-k", min=1, help="Number of memory results"),
    pref_top_k: int | None = typer.Option(None, "--pref-top-k", min=1, help="Number of preference results"),
    model_name_or_path: str | None = typer.Option(None, "--model", help="Chat model name"),
    system_prompt: str | None = typer.Option(None, "--system-prompt", help="Base system prompt"),
    max_tokens: int | None = typer.Option(None, "--max-tokens", min=1, help="Maximum generated tokens"),
    temperature: float | None = typer.Option(None, "--temperature", min=0.0, help="Sampling temperature"),
    top_p: float | None = typer.Option(None, "--top-p", min=0.0, max=1.0, help="Top-p sampling"),
    mem_cube_id: str | None = typer.Option(None, "--mem-cube-id", help="Single cube ID to use for chat"),
    readable_cube_ids: str | None = typer.Option(None, "--readable-cube-ids", help="JSON array of cube IDs user can read"),
    writable_cube_ids: str | None = typer.Option(None, "--writable-cube-ids", help="JSON array of cube IDs user can write"),
    history: str | None = typer.Option(None, "--history", help="JSON array of chat history messages"),
    filter_json: str | None = typer.Option(None, "--filter", help="JSON object for memory filtering"),
    threshold: float | None = typer.Option(None, "--threshold", min=0.0, max=1.0, help="Reference filtering threshold"),
    moscube: bool | None = typer.Option(None, "--moscube/--no-moscube", help="Use deprecated legacy MemOSCube pipeline"),
    include_preference: bool | None = typer.Option(None, "--include-preference/--no-include-preference", help="Include preference memories"),
    add_message_on_answer: bool | None = typer.Option(None, "--add-message-on-answer/--no-add-message-on-answer", help="Store the dialog after answering"),
    internet_search: bool | None = typer.Option(None, "--internet-search/--no-internet-search", help="Enable internet search"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Chat with MemOS."""
    cmd_chat(
        query,
        query_option=query_option,
        user_id=user_id,
        agent_id=agent_id,
        app_id=app_id,
        run_id=run_id,
        conversation_id=conversation_id,
        mode=mode,
        top_k=top_k,
        pref_top_k=pref_top_k,
        model_name_or_path=model_name_or_path,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        mem_cube_id=mem_cube_id,
        readable_cube_ids=readable_cube_ids,
        writable_cube_ids=writable_cube_ids,
        history=history,
        filter_json=filter_json,
        threshold=threshold,
        moscube=moscube,
        include_preference=include_preference,
        add_message_on_answer=add_message_on_answer,
        internet_search=internet_search,
        json_output=json_output,
    )


def get(
    memory_id: str = typer.Argument(..., help="Memory ID"),
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Get a specific memory by ID."""
    cmd_get(memory_id, user_id=user_id, json_output=json_output)


def delete(
    memory_id: str = typer.Argument(..., help="Memory ID to delete"),
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Delete a memory by ID."""
    cmd_delete(memory_id, user_id=user_id, json_output=json_output)
