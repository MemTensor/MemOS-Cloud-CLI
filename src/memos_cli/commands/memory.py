"""Typer entrypoints for memory operations."""
from __future__ import annotations

from typing import List
import typer

from memos_cli.commands.memory_cmd import (
    cmd_add,
    cmd_chat,
    cmd_delete,
    cmd_extract,
    cmd_feedback,
    cmd_get,
    cmd_rerank,
    cmd_search,
)

FORMAT_HELP = "Output format: table, markdown, agent, or json."
DETAIL_HELP = "Output detail: simple or detail."


def add(
    message: str | None = typer.Argument(None, help="Message content to add."),
    message_option: str | None = typer.Option(None, "--message", "-m", help="Message content to add."),
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Add messages."""
    cmd_add(
        message_text=message,
        message_option=message_option,
        user_id=user_id,
        conversation_id=None,
        agent_id=None,
        app_id=None,
        tags_json=None,
        info_json=None,
        allow_public=None,
        allow_knowledgebase_ids=None,
        async_mode=None,
        output_format=output_format,
        detail=None,
    )


def extract(
    message: str | None = typer.Argument(None, help="Message content to extract from."),
    message_option: str | None = typer.Option(None, "--message", "-m", help="Message content to extract from."),
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Extract memory candidates from messages without storing them."""
    cmd_extract(
        message_text=message,
        message_option=message_option,
        extraction_types=["memory", "preference"],
        user_id=user_id,
        agent_id=None,
        app_id=None,
        run_id=None,
        conversation_id=None,
        output_format=output_format,
        detail=None,
    )


def feedback(
    feedback_text: str | None = typer.Argument(None, help="Feedback content to add."),
    feedback_content: str | None = typer.Option(None, "--feedback-content", help="Feedback content to add."),
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Add feedback content."""
    cmd_feedback(
        feedback_text=feedback_text,
        feedback_content=feedback_content,
        user_id=user_id,
        agent_id=None,
        app_id=None,
        run_id=None,
        conversation_id=None,
        allow_knowledgebase_ids=None,
        output_format=output_format,
        detail=None,
    )


def search(
    query: str | None = typer.Argument(None, help="Search query"),
    query_option: str | None = typer.Option(None, "--query", "-q", help="Search query"),
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    memory_limit_number: int | None = typer.Option(None, "--memory-limit-number", min=1, help="Main memory recall count"),
    include_preference: str | None = typer.Option(None, "--include-preference", help="Include preference memory: true or false"),
    preference_limit_number: int | None = typer.Option(None, "--preference-limit-number", min=1, help="Preference memory recall count"),
    include_tool_memory: str | None = typer.Option(None, "--include-tool-memory", help="Include tool memory: true or false"),
    tool_memory_limit_number: int | None = typer.Option(None, "--tool-memory-limit-number", min=1, help="Tool memory recall count"),
    include_skill_memory: str | None = typer.Option(None, "--include-skill-memory", help="Include skill memory: true or false"),
    skill_memory_limit_number: int | None = typer.Option(None, "--skill-memory-limit-number", min=1, help="Skill memory recall count"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
    detail: str | None = typer.Option(None, "--detail", help=DETAIL_HELP),
):
    """Search memories."""
    cmd_search(
        query,
        query_option=query_option,
        user_id=user_id,
        conversation_id=None,
        filter_json=None,
        knowledgebase_ids=None,
        limit=memory_limit_number or 9,
        include_preference=include_preference,
        preference_limit=preference_limit_number or 9,
        include_tool_memory=include_tool_memory,
        tool_memory_limit=tool_memory_limit_number or 6,
        include_skill=include_skill_memory,
        skill_limit=skill_memory_limit_number or 6,
        relativity=None,
        output_format=output_format,
        detail=detail,
    )


def rerank(
    query: str | None = typer.Argument(None, help="Query used to rerank the candidate documents"),
    documents: List[str] | None = typer.Argument(None, help="Candidate documents"),
    query_option: str | None = typer.Option(None, "--query", "-q", help="Query used to rerank the candidate documents"),
    document_options: List[str] | None = typer.Option(None, "--documents", help="Candidate document, repeatable"),
    top_n: int | None = typer.Option(None, "--top-n", min=1, help="Return top N results only"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Rerank candidate documents."""
    cmd_rerank(
        query,
        documents=documents,
        query_option=query_option,
        document_options=document_options,
        documents_json=None,
        user_id=None,
        model=None,
        top_n=top_n,
        output_format=output_format,
        detail=None,
    )



def chat(
    query: str | None = typer.Argument(None, help="Chat query"),
    query_option: str | None = typer.Option(None, "--query", "-q", help="Chat query"),
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Chat with MemOS using documented request fields."""
    cmd_chat(
        query,
        query_option=query_option,
        user_id=user_id,
        agent_id=None,
        app_id=None,
        conversation_id=None,
        filter_json=None,
        knowledgebase_ids=None,
        memory_limit_number=9,
        include_preference=None,
        preference_limit_number=9,
        relativity=None,
        model_name=None,
        system_prompt=None,
        stream=None,
        max_tokens=None,
        temperature=None,
        top_p=None,
        add_message_on_answer=None,
        tags_json=None,
        info_json=None,
        allow_public=None,
        allow_knowledgebase_ids=None,
        output_format=output_format,
        detail=None,
    )


def get(
    user_id_arg: str | None = typer.Argument(None, help="User ID"),
    user_id: str | None = typer.Option(None, "--user-id", help="User ID"),
    page: int | None = typer.Option(None, "--page", min=1, help="Page number"),
    size: int | None = typer.Option(None, "--size", min=1, help="Page size"),
    include_preference: str | None = typer.Option(None, "--include-preference", help="Include preference memory: true or false"),
    include_tool_memory: str | None = typer.Option(None, "--include-tool-memory", help="Include tool memory: true or false"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
    detail: str | None = typer.Option(None, "--detail", help=DETAIL_HELP),
):
    """Get memories via the documented get_memory API."""
    cmd_get(
        user_id=user_id_arg or user_id,
        page=page,
        size=size,
        include_preference=include_preference,
        include_tool_memory=include_tool_memory,
        output_format=output_format,
        detail=detail,
    )


def delete(
    memory_id: str | None = typer.Argument(None, help="Memory ID"),
    user_id: str | None = typer.Option(None, "--user-id", help="Delete all memories for the given user ID"),
    output_format: str | None = typer.Option(None, "--format", help=FORMAT_HELP),
):
    """Delete memories."""
    cmd_delete(memory_id=memory_id, user_id=user_id, output_format=output_format, detail=None)
