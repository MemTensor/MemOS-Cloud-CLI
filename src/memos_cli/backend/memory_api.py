"""Memory-domain API wrapper for MemOS backend."""
from __future__ import annotations

import re
from typing import Any

from memos_cli.backend.normalizers import (
    extract_memory_list,
    normalize_chat_response,
    normalize_delete_response,
    normalize_kb_create_response,
    normalize_kb_delete_response,
    normalize_kb_file_delete_response,
    normalize_kb_file_add_response,
    normalize_kb_file_get_response,
    normalize_kb_list_response,
    normalize_rerank_response,
    normalize_search_response,
    normalize_single_memory_response,
)
from memos_cli.backend.transport import APIError, AuthError, MemOSTransport


class MemoryAPI:
    """Memory-specific route orchestration and response normalization."""

    _UUID_PATTERN = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )

    def __init__(self, transport: MemOSTransport):
        self.transport = transport

    def ping(self, timeout: float = 5.0) -> dict[str, Any]:
        """Ping the API to validate credentials."""
        for method, path in (("GET", "/v1/ping/"), ("GET", "/ping"), ("POST", "/search/memory")):
            try:
                if method == "POST":
                    return self.transport.request_json(
                        method,
                        path,
                        timeout=timeout,
                        json_body={
                            "query": "ping",
                            "user_id": "cli-healthcheck",
                            "memory_limit_number": 1,
                        },
                    )
                return self.transport.request_json(method, path, timeout=timeout)
            except AuthError:
                raise
            except Exception:
                continue
        raise APIError("Unable to reach MemOS API with the configured base URL")

    def add_memory(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Add messages."""
        message_payload: dict[str, Any] = {
            "messages": messages,
        }

        common_fields = [
            "user_id",
            "conversation_id",
            "agent_id",
            "app_id",
            "allow_knowledgebase_ids",
            "tags",
            "info",
            "allow_public",
            "async_mode",
        ]
        for field in common_fields:
            value = kwargs.get(field)
            if value is not None:
                message_payload[field] = value

        return self.transport.request_json("POST", "/add/message", json_body=message_payload)

    def add_feedback(self, feedback_content: str, **kwargs: Any) -> dict[str, Any]:
        """Add feedback content."""
        payload: dict[str, Any] = {
            "feedback_content": feedback_content,
        }
        common_fields = [
            "user_id",
            "conversation_id",
            "agent_id",
            "app_id",
            "allow_knowledgebase_ids",
        ]
        for field in common_fields:
            value = kwargs.get(field)
            if value is not None:
                payload[field] = value

        return self.transport.request_json("POST", "/add/feedback", json_body=payload)

    def extract_memory(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Extract memory candidates without storing them."""
        messages_payload: dict[str, Any] = {
            "messages": messages,
            "extraction_types": kwargs.get("extraction_types", ["memory", "preference"]),
        }
        common_fields = [
            "user_id",
            "conversation_id",
            "agent_id",
        ]
        for field in common_fields:
            value = kwargs.get(field)
            if value is not None:
                messages_payload[field] = value

        last_error: Exception | None = None
        attempts: list[tuple[list[str], dict[str, Any]]] = [
            (["/extract/memory", "/extract_memory"], messages_payload),
        ]
        for paths, payload in attempts:
            try:
                return self.transport.request_first_json("POST", paths, json_body=payload)
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise APIError("Failed to extract memory")

    def rerank_documents(self, query: str, documents: list[str], **kwargs: Any) -> dict[str, Any]:
        """Rerank candidate documents for a query."""
        payload: dict[str, Any] = {
            "model": kwargs.get("model") or "memos-reranker-0.6b",
            "query": query,
            "documents": documents,
        }
        if kwargs.get("user_id") is not None:
            payload["user_id"] = kwargs["user_id"]
        if kwargs.get("top_n") is not None:
            payload["top_n"] = kwargs["top_n"]

        data = self.transport.request_json("POST", "/rerank", json_body=payload)
        return normalize_rerank_response(data, query=query, documents=documents)

    def search_memories(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Search memories."""
        limit = kwargs.get("limit", 9)
        payload: dict[str, Any] = {
            "query": query,
            "memory_limit_number": limit,
            "include_preference": kwargs.get("include_preference", True),
        }
        # Only include non-None values
        if kwargs.get("user_id"):
            payload["user_id"] = kwargs["user_id"]
        if kwargs.get("conversation_id"):
            payload["conversation_id"] = kwargs["conversation_id"]
        if kwargs.get("agent_id"):
            payload["agent_id"] = kwargs["agent_id"]
        if kwargs.get("app_id"):
            payload["app_id"] = kwargs["app_id"]
        if kwargs.get("filter") is not None:
            payload["filter"] = kwargs["filter"]
        if kwargs.get("knowledgebase_ids"):
            payload["knowledgebase_ids"] = kwargs["knowledgebase_ids"]
        if kwargs.get("preference_limit") is not None:
            payload["preference_limit_number"] = kwargs["preference_limit"]
        if kwargs.get("include_tool_memory") is not None:
            payload["include_tool_memory"] = kwargs["include_tool_memory"]
        payload["tool_memory_limit_number"] = kwargs.get("tool_memory_limit", 6)
        if kwargs.get("include_skill") is not None:
            payload["include_skill"] = kwargs["include_skill"]
        payload["skill_limit_number"] = kwargs.get("skill_limit", 6)
        if kwargs.get("relativity") is not None:
            payload["relativity"] = kwargs["relativity"]

        data = self.transport.request_first_json(
            "POST", ["/search/memory", "/v1/memories/search/"], json_body=payload
        )
        return data

    def get_memories(self, **kwargs: Any) -> dict[str, Any]:
        """Get memories using the documented /get/memory API."""
        user_id = kwargs.get("user_id")
        if not user_id:
            raise APIError("Get memory requires user_id")

        payload: dict[str, Any] = {"user_id": user_id}
        if kwargs.get("page") is not None:
            payload["page"] = kwargs["page"]
        if kwargs.get("size") is not None:
            payload["size"] = kwargs["size"]
        if kwargs.get("include_preference") is not None:
            payload["include_preference"] = kwargs["include_preference"]
        if kwargs.get("include_tool_memory") is not None:
            payload["include_tool_memory"] = kwargs["include_tool_memory"]

        data = self.transport.request_json(
            "POST",
            "/get/memory",
            json_body=payload,
            include_tracking_headers=False,
        )
        return data

    def chat(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Chat with MemOS using a non-streaming response route."""
        user_id = kwargs.get("user_id")
        if not user_id:
            raise APIError("Chat requires user_id")

        payload: dict[str, Any] = {
            "user_id": user_id,
            "conversation_id": kwargs.get("conversation_id"),
            "query": query,
        }
        field_names = [
            "filter",
            "knowledgebase_ids",
            "memory_limit_number",
            "include_preference",
            "preference_limit_number",
            "relativity",
            "model_name",
            "system_prompt",
            "stream",
            "max_tokens",
            "temperature",
            "top_p",
            "add_message_on_answer",
            "app_id",
            "agent_id",
            "tags",
            "info",
            "allow_public",
            "allow_knowledgebase_ids",
        ]
        for field in field_names:
            value = kwargs.get(field)
            if value is not None:
                payload[field] = value

        data = self.transport.request_json("POST", "/chat", json_body=payload)
        return normalize_chat_response(data, original_query=query)

    def create_knowledgebase(
        self,
        name: str,
        *,
        description: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a knowledge base."""
        payload: dict[str, Any] = {
            "knowledgebase_name": name,
        }
        if description is not None:
            payload["knowledgebase_description"] = description

        data = self.transport.request_json(
            "POST",
            "/create/knowledgebase",
            json_body=payload,
        )
        return normalize_kb_create_response(data, name=name, description=description)

    def list_knowledgebases(self, **kwargs: Any) -> list[dict[str, Any]]:
        """List knowledge bases.

        Public docs do not currently expose this route clearly; use route fallbacks.
        """
        data = self.transport.request_first_json(
            "POST",
            [
                "/get/knowledgebase",
                "/list/knowledgebase",
                "/get/knowledgebases",
            ],
            json_body={},
        )
        return normalize_kb_list_response(data)

    def add_knowledgebase_files(
        self,
        knowledgebase_id: str,
        files: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Add files to a knowledge base."""
        payload = {
            "knowledgebase_id": knowledgebase_id,
            "file": files,
        }
        data = self.transport.request_json(
            "POST",
            "/add/knowledgebase-file",
            json_body=payload,
        )
        return normalize_kb_file_add_response(data, knowledgebase_id=knowledgebase_id)

    def get_knowledgebase_file(
        self,
        file_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Get a knowledge base file/document by document id.

        The documentation references a get-kb-doc endpoint. Body field naming is
        handled compatibly via `id` then `file_id`.
        """
        last_error: Exception | None = None
        for payload in ({"id": file_id}, {"file_id": file_id}):
            try:
                data = self.transport.request_first_json(
                    "POST",
                    [
                        "/get/knowledgebase-file",
                        "/get/knowledgebase-doc",
                    ],
                    json_body=payload,
                )
                return normalize_kb_file_get_response(data)
            except Exception as exc:
                last_error = exc

        if last_error is not None:
            raise last_error
        raise APIError("Failed to get knowledge base file")

    def delete_knowledgebase_files(
        self,
        file_ids: list[str],
        knowledgebase_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Delete files from a knowledge base.

        Public docs indicate knowledge-base document operations are available; keep
        `knowledgebase_id` optional for routes that don't require it.
        """
        payload: dict[str, Any] = {"file_ids": file_ids}
        if knowledgebase_id:
            payload["knowledgebase_id"] = knowledgebase_id
        data = self.transport.request_first_json(
            "POST",
            [
                "/delete/knowledgebase-file",
                "/remove/knowledgebase-file",
            ],
            json_body=payload,
        )
        return normalize_kb_file_delete_response(
            data,
            knowledgebase_id=knowledgebase_id,
            file_ids=file_ids,
        )

    def delete_knowledgebase(
        self,
        knowledgebase_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Delete a knowledge base.

        Route names are inferred from the documented create/add naming pattern.
        """
        payload = {"knowledgebase_id": knowledgebase_id}
        data = self.transport.request_first_json(
            "POST",
            [
                "/remove/knowledgebase",
                "/delete/knowledgebase",
            ],
            json_body=payload,
        )
        return normalize_kb_delete_response(data, knowledgebase_id=knowledgebase_id)

    @staticmethod
    def _find_memory_by_id(memories: list[dict[str, Any]], memory_id: str) -> dict[str, Any] | None:
        exact_match: dict[str, Any] | None = None
        prefix_matches: list[dict[str, Any]] = []

        for memory in memories:
            current_id = str(memory.get("id") or "")
            if not current_id:
                continue
            if current_id == memory_id:
                exact_match = memory
                break
            if current_id.startswith(memory_id):
                prefix_matches.append(memory)

        if exact_match:
            return exact_match
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        return None

    @classmethod
    def _looks_like_full_memory_id(cls, memory_id: str) -> bool:
        return bool(cls._UUID_PATTERN.fullmatch(memory_id))

    def get_memory(self, memory_id: str, **kwargs: Any) -> dict[str, Any]:
        """Get a specific memory."""
        memory_id = memory_id.strip()
        user_id = kwargs.get("user_id")
        last_error: Exception | None = None
        matched: dict[str, Any] | None = None

        if user_id:
            try:
                page = 1
                while page <= 3:
                    data = self.transport.request_json(
                        "POST",
                        "/get/memory",
                        json_body={
                            "user_id": user_id,
                            "page": page,
                            "size": 50,
                            "include_preference": True,
                            "include_tool_memory": True,
                        },
                    )
                    memories = normalize_search_response(data)
                    matched = self._find_memory_by_id(memories, memory_id)
                    if matched:
                        return matched

                    pages = data.get("data", {}).get("pages", 0)
                    if not pages or page >= pages:
                        break
                    page += 1
            except Exception as exc:
                last_error = exc

            try:
                data = self.transport.request_json(
                    "GET",
                    "/memories",
                    params={"user_id": user_id},
                )
                memories = extract_memory_list(data)
                matched = self._find_memory_by_id(memories, memory_id)
                if matched:
                    return matched
            except Exception as exc:
                last_error = exc

        if not self._looks_like_full_memory_id(memory_id):
            raise APIError(f"Memory not found: {memory_id}")

        try:
            data = self.transport.request_first_json(
                "POST",
                ["/get_memory_by_ids", "/get/memory_by_ids"],
                json_body={
                    "memory_ids": [memory_id],
                    **({"user_id": user_id} if user_id else {}),
                },
            )
            normalized = extract_memory_list(data)
            matched = self._find_memory_by_id(normalized, memory_id)
            if matched:
                return matched
        except Exception as exc:
            last_error = exc

        try:
            data = self.transport.request_first_json(
                "GET",
                [f"/get_memory/{memory_id}", f"/v1/memories/{memory_id}/"],
            )
            normalized = normalize_single_memory_response(data, memory_id)
            if normalized:
                return normalized
        except Exception as exc:
            last_error = exc

        if last_error is not None:
            raise last_error
        raise APIError(f"Memory not found: {memory_id}")

    def delete_memory(self, memory_ids: list[str], **kwargs: Any) -> dict[str, Any]:
        """Delete memories using the documented API."""
        payload: dict[str, Any] = {}
        if memory_ids:
            payload["memory_ids"] = memory_ids
        if kwargs.get("user_id") is not None:
            payload["user_id"] = kwargs["user_id"]

        return self.transport.request_json(
            "POST",
            "/delete/memory",
            json_body=payload,
        )
