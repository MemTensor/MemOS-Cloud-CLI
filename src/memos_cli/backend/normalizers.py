"""Response normalizers for MemOS API payloads."""
from __future__ import annotations


def normalize_add_response(data: dict, *, original_text: str) -> dict:
    """Normalize add response to a stable CLI shape."""
    if isinstance(data.get("results"), list):
        return data
    if isinstance(data.get("data"), list):
        return {
            "results": [
                normalize_memory_item(item, fallback_text=original_text) for item in data["data"]
            ]
        }
    if isinstance(data.get("data"), dict):
        return {"results": [normalize_memory_item(data["data"], fallback_text=original_text)]}
    return {"results": [{"memory": original_text, **data}]}


def normalize_chat_response(data: dict | str, *, original_query: str) -> dict:
    """Normalize chat response to a stable CLI shape."""
    if isinstance(data, str):
        return {"answer": data, "query": original_query}

    answer = (
        data.get("answer")
        or data.get("response")
        or _extract_chat_data_field(data.get("data"))
        or _extract_choice_content(data.get("choices"))
        or ""
    )
    normalized = dict(data)
    normalized["answer"] = answer
    normalized.setdefault("query", original_query)
    return normalized


def normalize_kb_create_response(data: dict, *, name: str, description: str | None) -> dict:
    """Normalize knowledge base creation response."""
    normalized = dict(data)
    kb_data = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
    normalized["id"] = kb_data.get("id") or data.get("id") or ""
    normalized.setdefault("knowledgebase_name", name)
    if description is not None:
        normalized.setdefault("knowledgebase_description", description)
    return normalized


def normalize_kb_file_add_response(data: dict, *, knowledgebase_id: str) -> dict:
    """Normalize knowledge base file add response."""
    normalized = dict(data)
    normalized.setdefault("knowledgebase_id", knowledgebase_id)
    files = data.get("data", [])
    if isinstance(files, list):
        normalized["files"] = files
    else:
        normalized["files"] = []
    return normalized


def normalize_search_response(data: dict) -> list[dict]:
    """Normalize search response to a flat memory list."""
    if isinstance(data.get("results"), list):
        return _sort_by_relativity_desc([normalize_memory_item(item) for item in data["results"]])

    raw_data = data.get("data", data)
    if isinstance(raw_data, list):
        return _sort_by_relativity_desc([normalize_memory_item(item) for item in raw_data])

    memory_list = raw_data.get("memory_detail_list", []) if isinstance(raw_data, dict) else []
    preference_list = (
        raw_data.get("preference_detail_list", []) if isinstance(raw_data, dict) else []
    )
    tool_list = raw_data.get("tool_memory_detail_list", []) if isinstance(raw_data, dict) else []

    results = [normalize_memory_item(item) for item in memory_list]
    results.extend(normalize_preference_item(item) for item in preference_list)
    results.extend(normalize_memory_item(item) for item in tool_list)
    return _sort_by_relativity_desc(results)


def normalize_single_memory_response(data: dict, memory_id: str) -> dict | None:
    """Normalize single-memory fetch responses across route variants."""
    if "memory" in data or "text" in data or "memory_value" in data:
        return normalize_memory_item(data)
    memories = extract_memory_list(data)
    for memory in memories:
        if memory.get("id") == memory_id:
            return memory
    return memories[0] if memories else None


def extract_memory_list(data: dict) -> list[dict]:
    """Extract memory list from various API response envelopes."""
    raw_data = data.get("data", data)
    if isinstance(raw_data, dict) and isinstance(raw_data.get("memories"), list):
        return [normalize_memory_item(item) for item in raw_data["memories"]]
    if isinstance(raw_data, dict):
        text_mem = raw_data.get("text_mem", [])
        extracted: list[dict] = []
        for bucket in text_mem:
            memories = bucket.get("memories", []) if isinstance(bucket, dict) else []
            extracted.extend(normalize_memory_item(item) for item in memories)
        return extracted
    return []


def normalize_delete_response(data: dict, memory_id: str) -> dict:
    """Normalize delete response to a stable CLI shape."""
    if not data:
        return {"deleted": True, "id": memory_id}
    if "deleted" in data:
        return {"id": memory_id, **data}
    code = data.get("code")
    deleted = code in {0, 200, None}
    return {"deleted": deleted, "id": memory_id, "raw": data}


def normalize_memory_item(item: dict, fallback_text: str | None = None) -> dict:
    """Normalize a memory-like record."""
    memory_text = (
        item.get("memory")
        or item.get("text")
        or item.get("memory_value")
        or item.get("content")
        or fallback_text
        or ""
    )
    normalized = dict(item)
    normalized["memory"] = memory_text
    if "memory_id" in normalized and "id" not in normalized:
        normalized["id"] = normalized["memory_id"]
    if normalized.get("created_at") is None and normalized.get("create_time") is not None:
        normalized["created_at"] = normalized["create_time"]
    if normalized.get("updated_at") is None and normalized.get("update_time") is not None:
        normalized["updated_at"] = normalized["update_time"]
    if normalized.get("score") is None and normalized.get("relativity") is not None:
        normalized["score"] = normalized["relativity"]
    return normalized


def normalize_preference_item(item: dict) -> dict:
    """Normalize a preference-like record into memory shape."""
    normalized = dict(item)
    normalized["memory"] = item.get("preference", "")
    if "preference_id" in item and "id" not in normalized:
        normalized["id"] = item["preference_id"]
    normalized.setdefault("memory_type", item.get("preference_type", "preference"))
    if normalized.get("created_at") is None and normalized.get("create_time") is not None:
        normalized["created_at"] = normalized["create_time"]
    if normalized.get("updated_at") is None and normalized.get("update_time") is not None:
        normalized["updated_at"] = normalized["update_time"]
    if normalized.get("score") is None and normalized.get("relativity") is not None:
        normalized["score"] = normalized["relativity"]
    return normalized


def _extract_chat_data_field(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return (
            value.get("answer")
            or value.get("response")
            or value.get("content")
            or value.get("text")
            or ""
        )
    return ""


def _extract_choice_content(choices) -> str:
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    if isinstance(first.get("text"), str):
        return first["text"]
    return ""


def _sort_by_relativity_desc(items: list[dict]) -> list[dict]:
    def relativity_value(item: dict) -> float:
        value = item.get("relativity")
        if value is None:
            value = item.get("score")
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("-inf")

    return sorted(items, key=relativity_value, reverse=True)
