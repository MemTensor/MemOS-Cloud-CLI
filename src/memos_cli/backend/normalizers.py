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


def normalize_feedback_response(data: dict, *, feedback_content: str) -> dict:
    """Normalize feedback response to a stable CLI shape."""
    normalized = dict(data) if data else {}
    normalized.setdefault("feedback_content", feedback_content)
    normalized.setdefault("status", data.get("status") if data else "success")
    return normalized


def normalize_extract_response(data: dict, *, original_text: str) -> dict:
    """Normalize extract response to a stable CLI shape."""
    if isinstance(data.get("results"), list):
        return {"results": [normalize_memory_item(item, fallback_text=original_text) for item in data["results"]]}

    raw_data = data.get("data", data)
    if isinstance(raw_data, list):
        return {
            "results": [normalize_memory_item(item, fallback_text=original_text) for item in raw_data]
        }
    if isinstance(raw_data, dict):
        if isinstance(raw_data.get("memories"), list):
            return {
                "results": [
                    normalize_memory_item(item, fallback_text=original_text)
                    for item in raw_data["memories"]
                ]
            }
        if isinstance(raw_data.get("results"), list):
            return {
                "results": [
                    normalize_memory_item(item, fallback_text=original_text)
                    for item in raw_data["results"]
                ]
            }
        return {"results": [normalize_memory_item(raw_data, fallback_text=original_text)]}
    return {"results": [{"memory": original_text, **data}]}


def normalize_rerank_response(data: dict, *, query: str, documents: list[str]) -> dict:
    """Normalize rerank response to a stable CLI shape."""
    normalized = dict(data) if data else {}
    raw_results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw_results, list) and isinstance(data, dict):
        raw_data = data.get("data")
        if isinstance(raw_data, dict):
            raw_results = raw_data.get("results")
    if not isinstance(raw_results, list):
        raw_results = []

    results: list[dict] = []
    for rank, item in enumerate(raw_results, 1):
        if not isinstance(item, dict):
            continue
        current = dict(item)
        index = current.get("index")
        if isinstance(index, int) and 0 <= index < len(documents):
            fallback_text = documents[index]
        else:
            fallback_text = ""

        document = current.get("document")
        if isinstance(document, dict):
            text = document.get("text") or fallback_text
        elif isinstance(document, str):
            text = document or fallback_text
            document = {"text": text}
        else:
            text = fallback_text
            document = {"text": text}

        current["document"] = document
        current["text"] = text
        current.setdefault("relevance_score", current.get("score"))
        current["rank"] = rank
        results.append(current)

    normalized["query"] = query
    normalized["documents"] = documents
    normalized["results"] = results
    return normalized


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


def normalize_kb_list_response(data: dict) -> list[dict]:
    """Normalize knowledge base listing response."""
    raw_data = data.get("data", data)
    if isinstance(raw_data, list):
        return [dict(item) for item in raw_data if isinstance(item, dict)]
    if isinstance(raw_data, dict):
        if isinstance(raw_data.get("knowledgebases"), list):
            return [dict(item) for item in raw_data["knowledgebases"] if isinstance(item, dict)]
        if isinstance(raw_data.get("items"), list):
            return [dict(item) for item in raw_data["items"] if isinstance(item, dict)]
    return []


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


def normalize_kb_file_get_response(data: dict) -> dict:
    """Normalize knowledge base file get response."""
    raw_data = data.get("data", data)
    if isinstance(raw_data, dict):
        return dict(raw_data)
    if isinstance(raw_data, list) and raw_data and isinstance(raw_data[0], dict):
        return dict(raw_data[0])
    return {}


def normalize_kb_delete_response(data: dict, *, knowledgebase_id: str) -> dict:
    """Normalize knowledge base delete response."""
    normalized = dict(data) if data else {}
    normalized.setdefault("knowledgebase_id", knowledgebase_id)
    normalized.setdefault("deleted", data.get("code") in {0, 200, None} if data else True)
    return normalized


def normalize_kb_file_delete_response(
    data: dict,
    *,
    knowledgebase_id: str | None = None,
    file_ids: list[str],
) -> dict:
    """Normalize knowledge base file delete response."""
    normalized = dict(data) if data else {}
    if knowledgebase_id is not None:
        normalized.setdefault("knowledgebase_id", knowledgebase_id)
    normalized.setdefault("file_ids", file_ids)
    normalized.setdefault("deleted", data.get("code") in {0, 200, None} if data else True)
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
