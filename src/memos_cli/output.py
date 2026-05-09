"""Output formatting for MemOS CLI — text, JSON, table modes."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from rich.console import Console
from rich.table import Table
from rich.text import Text

from memos_cli.branding import ACCENT_COLOR, BRAND_COLOR, DIM_COLOR


def format_memories_text(
    console: Console,
    memories: list[dict],
    title: str = "memories",
    *,
    show_relativity: bool = True,
) -> None:
    """Render memories in table mode with type and time information."""
    count = len(memories)
    if count == 0:
        console.print(f"\n[bold {BRAND_COLOR}]Found 0 {title}.[/]\n")
        return

    table = Table(
        title=f"Found {count} {title}",
        title_style=f"bold {BRAND_COLOR}",
        header_style=f"bold {ACCENT_COLOR}",
        border_style=BRAND_COLOR,
        show_lines=False,
        expand=False,
        pad_edge=False,
    )
    table.add_column("#", style="bold", width=4, no_wrap=True, justify="center", vertical="middle")
    table.add_column(
        "ID",
        style=DIM_COLOR,
        min_width=30,
        width=40,
        no_wrap=True,
        justify="center",
        vertical="middle",
    )
    table.add_column(
        "Memory",
        style="white",
        min_width=20,
        max_width=40,
        no_wrap=False,
        overflow="fold",
        justify="left",
        vertical="middle",
    )
    table.add_column("Type", style=ACCENT_COLOR, width=24, no_wrap=True, justify="center", vertical="middle")
    table.add_column("Created", style=DIM_COLOR, width=18, no_wrap=True, justify="center", vertical="middle")
    if show_relativity:
        table.add_column("Score", style=DIM_COLOR, width=12, no_wrap=True, justify="center", vertical="middle")

    for i, mem in enumerate(memories, 1):
        row_style = "dim" if i % 2 == 0 else "none"
        memory_text = mem.get("memory", mem.get("text", "")) or ""
        mem_type = _memory_type_label(mem)
        created = mem.get("create_time")
        if created is None:
            created = mem.get("created_at")
        created_display = _format_date(created) or "-"
        score = mem.get("relativity")
        if score is None:
            score = mem.get("score")
        mem_id = str(mem.get("id", "") or "-")
        cells: list[Text] = [
            Text(str(i), style="bold"),
            Text(mem_id, style=row_style),
            Text(memory_text, style=row_style),
            Text(str(mem_type), style=row_style),
            Text(created_display, style=row_style),
        ]
        if show_relativity:
            cells.append(Text(_format_score(score), style=row_style))
        table.add_row(*cells)

    console.print()
    console.print(table)
    console.print()


def format_json(console: Console, data: Any) -> None:
    """Output data as pretty-printed JSON."""
    console.print_json(json.dumps(data, default=str))


def format_single_memory(console: Console, mem: dict, output: str = "text") -> None:
    """Format a single memory for display."""
    if output == "json":
        format_json(console, mem)
        return

    format_memories_text(console, [mem], title="memory", show_relativity=False)


def format_add_result(console: Console, result: dict | list, output: str = "text") -> None:
    """Format the result of an add operation."""
    if output == "json":
        format_json(console, result)
        return
    
    if output == "quiet":
        return
    
    results = result if isinstance(result, list) else result.get("results", [result])
    
    if not results:
        console.print("  [dim]No memories extracted.[/]")
        return
    
    console.print()


def format_extract_result(console: Console, result: dict | list, output: str = "text") -> None:
    """Format the result of an extract operation."""
    if output == "json":
        format_json(console, result)
        return

    if output == "quiet":
        return

    results = result if isinstance(result, list) else result.get("results", [result])

    if not results:
        console.print("  [dim]No memories extracted.[/]")
        return

    console.print()

    for r in results:
        memory = r.get("memory") or r.get("text") or ""
        parts = ["[cyan]~[/][dim]Extracted [/]"]
        if memory:
            parts.append(f"[white]{memory}[/]")
        console.print("  ".join(parts))

    console.print()
    
    for r in results:
        memory = r.get("memory") or r.get("text") or ""
        mem_id = r.get("id") or r.get("memory_id") or ""
        
        icon = "[green]+[/]"
        label = "Added"
        
        parts = [f"{icon}[dim]{label:<10}[/]"]
        if memory:
            parts.append(f"[white]{memory}[/]")
        if mem_id:
            parts.append(f"[dim]({mem_id})[/]")
        
        console.print("  ".join(parts))
    
    console.print()


def format_chat_result(console: Console, result: dict, output: str = "text") -> None:
    """Format chat output."""
    if output == "json":
        format_json(console, result)
        return

    answer = result.get("answer", "")
    if answer:
        console.print()
        console.print(answer)
        console.print()
        return

    console.print("  [dim]No chat response returned.[/]")


def format_kb_create_result(console: Console, result: dict, output: str = "text") -> None:
    """Format knowledge base creation result."""
    if output == "json":
        format_json(console, result)
        return

    kb_id = result.get("id", "")
    name = result.get("knowledgebase_name", "")
    message = result.get("message", "")

    console.print()
    if kb_id:
        console.print(f"[green]✓[/] Knowledge base created: [white]{name}[/] [dim]({kb_id})[/]")
    else:
        console.print(f"[green]✓[/] Knowledge base created: [white]{name}[/]")
    if message:
        console.print(f"[dim]{message}[/]")
    console.print()


def format_kb_list_result(console: Console, items: list[dict], output: str = "text") -> None:
    """Format knowledge base listing."""
    if output == "json":
        format_json(console, items)
        return

    if not items:
        console.print()
        console.print(f"[bold {BRAND_COLOR}]Found 0 knowledge bases.[/]")
        console.print()
        return

    table = Table(
        title=f"Found {len(items)} knowledge bases",
        title_style=f"bold {BRAND_COLOR}",
        header_style=f"bold {ACCENT_COLOR}",
        border_style=BRAND_COLOR,
        show_lines=False,
        expand=False,
        pad_edge=False,
    )
    table.add_column("#", style="bold", width=4, no_wrap=True, justify="center")
    table.add_column("id", style=DIM_COLOR, min_width=16, width=32, no_wrap=True)
    table.add_column("knowledgebase_name", style="white", min_width=16, max_width=32, overflow="fold")
    table.add_column("knowledgebase_description", style=DIM_COLOR, min_width=16, max_width=40, overflow="fold")

    for i, item in enumerate(items, 1):
        table.add_row(
            str(i),
            str(item.get("id", "") or item.get("knowledgebase_id", "") or "-"),
            str(item.get("knowledgebase_name", "") or item.get("name", "") or "-"),
            str(item.get("knowledgebase_description", "") or item.get("description", "") or "-"),
        )

    console.print()
    console.print(table)
    console.print()


def format_kb_file_add_result(console: Console, result: dict, output: str = "text") -> None:
    """Format knowledge base file add result."""
    if output == "json":
        format_json(console, result)
        return

    knowledgebase_id = result.get("knowledgebase_id", "")
    files = result.get("files", [])

    console.print()
    console.print(f"[green]✓[/] Added {len(files)} file(s) to knowledge base [dim]{knowledgebase_id}[/]")
    for item in files:
        content = item.get("content") if isinstance(item, dict) else ""
        if content:
            console.print(f"  [white]{content}[/]")
    console.print()


def format_kb_delete_result(console: Console, result: dict, output: str = "text") -> None:
    """Format knowledge base delete result."""
    if output == "json":
        format_json(console, result)
        return

    knowledgebase_id = result.get("knowledgebase_id", "")
    message = result.get("message", "")

    console.print()
    console.print(f"[green]✓[/] Knowledge base deleted: [dim]{knowledgebase_id}[/]")
    if message:
        console.print(f"[dim]{message}[/]")
    console.print()


def format_kb_file_get_result(console: Console, item: dict, output: str = "text") -> None:
    """Format knowledge base file get result."""
    if output == "json":
        format_json(console, item)
        return

    if not item:
        console.print()
        console.print(f"[bold {BRAND_COLOR}]Found 0 files.[/]")
        console.print()
        return

    table = Table(
        title="Knowledge base document",
        title_style=f"bold {BRAND_COLOR}",
        header_style=f"bold {ACCENT_COLOR}",
        border_style=BRAND_COLOR,
        show_lines=False,
        expand=False,
        pad_edge=False,
    )
    table.add_column("id", style=DIM_COLOR, min_width=16, width=32, no_wrap=True)
    table.add_column("name", style="white", min_width=20, max_width=48, overflow="fold")
    table.add_column("status", style=ACCENT_COLOR, width=12, no_wrap=True, justify="center")
    table.add_column("sizeMB", style=DIM_COLOR, width=10, no_wrap=True, justify="right")

    size = item.get("sizeMB")
    if isinstance(size, (int, float)):
        size_text = f"{size:.2f}"
    else:
        size_text = "-" if size is None else str(size)
    table.add_row(
        str(item.get("id", "") or "-"),
        str(item.get("name", "") or item.get("content", "") or "-"),
        str(item.get("status", "") or "-"),
        size_text,
    )

    console.print()
    console.print(table)
    console.print()


def format_kb_file_delete_result(console: Console, result: dict, output: str = "text") -> None:
    """Format knowledge base file delete result."""
    if output == "json":
        format_json(console, result)
        return

    knowledgebase_id = result.get("knowledgebase_id", "")
    file_ids = result.get("file_ids", [])
    message = result.get("message", "")

    console.print()
    console.print(
        f"[green]✓[/] Deleted {len(file_ids)} file(s) from knowledge base [dim]{knowledgebase_id}[/]"
    )
    for file_id in file_ids:
        console.print(f"  [dim]{file_id}[/]")
    if message:
        console.print(f"[dim]{message}[/]")
    console.print()


def format_rerank_result(console: Console, result: dict, output: str = "text") -> None:
    """Format rerank output."""
    if output == "json":
        format_json(console, result)
        return

    items = result.get("results", []) if isinstance(result, dict) else []
    if not items:
        console.print()
        console.print(f"[bold {BRAND_COLOR}]Found 0 rerank results.[/]")
        console.print()
        return

    table = Table(
        title=f"Found {len(items)} rerank results",
        title_style=f"bold {BRAND_COLOR}",
        header_style=f"bold {ACCENT_COLOR}",
        border_style=BRAND_COLOR,
        show_lines=False,
        expand=False,
        pad_edge=False,
    )
    table.add_column("#", style="bold", width=4, no_wrap=True, justify="center")
    table.add_column("score", style=ACCENT_COLOR, width=10, no_wrap=True, justify="right")
    table.add_column(
        "document",
        style="white",
        min_width=24,
        max_width=80,
        no_wrap=False,
        overflow="fold",
    )

    for item in items:
        score = item.get("relevance_score")
        if score is None:
            score = item.get("score")
        text = item.get("text") or item.get("document", {}).get("text") or ""
        table.add_row(
            str(item.get("rank") or len(table.rows) + 1),
            _format_score(score),
            str(text),
        )

    console.print()
    console.print(table)
    console.print()


def format_agent_envelope(
    console: Console,
    *,
    command: str,
    data: Any,
    duration_ms: int | None = None,
    scope: dict | None = None,
    count: int | None = None,
):
    """Output structured JSON envelope for agent/programmatic use (--json mode)."""
    envelope: dict[str, Any] = {
        "status": "success",
        "command": command,
    }
    
    if duration_ms is not None:
        envelope["duration_ms"] = duration_ms
    
    if scope:
        filtered = {k: v for k, v in scope.items() if v}
        if filtered:
            envelope["scope"] = filtered
    
    if count is not None:
        envelope["count"] = count
    
    envelope["data"] = data
    
    console.print_json(json.dumps(envelope, default=str))


def _format_date(date_value: Any) -> str | None:
    """Format ISO date strings or unix timestamps to readable format."""
    if date_value is None or date_value == "":
        return None
    try:
        if isinstance(date_value, (int, float)):
            timestamp = float(date_value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000.0
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M")
        date_str = str(date_value)
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(date_value)


def _memory_type_label(mem: dict) -> str:
    raw = (
        mem.get("memory_type")
        or mem.get("type")
        or mem.get("preference_type")
        or "memory"
    )
    text = str(raw).replace("_", " ").strip()
    if not text:
        return "memory"
    return text


def _format_score(score: Any) -> str:
    if score is None:
        return "-"
    try:
        return f"{float(score):.2f}"
    except (TypeError, ValueError):
        return str(score)
