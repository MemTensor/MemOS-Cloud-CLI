"""Memory-domain API wrapper for MemOS backend."""
from __future__ import annotations

from typing import Any

from memos_cli.backend.normalizers import (
    extract_memory_list,
    normalize_add_response,
    normalize_chat_response,
    normalize_delete_response,
    normalize_extract_response,
    normalize_feedback_response,
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

    def add_memory(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Add a new memory."""
        text_payload: dict[str, Any] = {
            "text": text,
            "source": "cli",
        }
        message_payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": text}],
            "source": "cli",
        }

        common_fields = [
            "user_id",
            "conversation_id",
            "agent_id",
            "app_id",
            "run_id",
            "allow_knowledgebase_ids",
            "tags",
        ]
        for field in common_fields:
            value = kwargs.get(field)
            if value is not None:
                text_payload[field] = value
                message_payload[field] = value

        last_error: Exception | None = None

        try:
            data = self.transport.request_json("POST", "/v1/memories/", json_body=text_payload)
            return normalize_add_response(data, original_text=text)
        except Exception as exc:
            last_error = exc

        try:
            data = self.transport.request_json("POST", "/add/message", json_body=message_payload)
            return normalize_add_response(data, original_text=text)
        except Exception as exc:
            last_error = exc

        if last_error is not None:
            raise last_error
        raise APIError("Failed to add memory")

    def add_feedback(self, feedback_content: str, **kwargs: Any) -> dict[str, Any]:
        """Add feedback content."""
        payload: dict[str, Any] = {
            "feedback_content": feedback_content,
            "source": "cli",
        }
        common_fields = [
            "user_id",
            "conversation_id",
            "agent_id",
            "app_id",
            "run_id",
            "allow_knowledgebase_ids",
        ]
        for field in common_fields:
            value = kwargs.get(field)
            if value is not None:
                payload[field] = value

        data = self.transport.request_json("POST", "/add/feedback", json_body=payload)
        return normalize_feedback_response(data, feedback_content=feedback_content)

    def extract_memory(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Extract memory candidates without storing them."""
        messages_payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": text}],
            "extraction_types": kwargs.get("extraction_types", ["memory", "preference"]),
            "source": "cli",
        }
        common_fields = [
            "user_id",
            "conversation_id",
            "agent_id",
            "app_id",
            "run_id",
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
                data = self.transport.request_first_json("POST", paths, json_body=payload)
                return normalize_extract_response(data, original_text=text)
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

    def search_memories(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Search memories."""
        payload: dict[str, Any] = {
            "query": query,
            "source": "cli",
            "memory_limit_number": kwargs.get("limit", 10),
            "include_preference": True,
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
        if kwargs.get("run_id"):
            payload["run_id"] = kwargs["run_id"]
        if kwargs.get("knowledgebase_ids"):
            payload["knowledgebase_ids"] = kwargs["knowledgebase_ids"]

        data = self.transport.request_first_json(
            "POST", ["/search/memory", "/v1/memories/search/"], json_body=payload
        )
        return normalize_search_response(data)

    def list_memories(self, **kwargs: Any) -> list[dict[str, Any]]:
        """List memories for the resolved user."""
        user_id = kwargs.get("user_id")
        limit = kwargs.get("limit")
        page_size = min(kwargs.get("page_size", 50), 50)

        if limit is not None and limit < 1:
            return []

        collected: list[dict[str, Any]] = []
        last_error: Exception | None = None

        if user_id:
            try:
                page = 1
                while True:
                    data = self.transport.request_json(
                        "POST",
                        "/get/memory",
                        json_body={
                            "user_id": user_id,
                            "page": page,
                            "size": page_size,
                            "include_preference": True,
                            "include_tool_memory": True,
                        },
                    )
                    memories = normalize_search_response(data)
                    collected.extend(memories)

                    if limit is not None and len(collected) >= limit:
                        return collected[:limit]

                    pages = data.get("data", {}).get("pages", 0)
                    if not pages or page >= pages or not memories:
                        break
                    page += 1
                return collected
            except Exception as exc:
                last_error = exc

        try:
            params = {"user_id": user_id} if user_id else None
            data = self.transport.request_first_json(
                "GET",
                ["/memories", "/v1/memories/"],
                params=params,
            )
            memories = extract_memory_list(data)
            if limit is not None:
                return memories[:limit]
            return memories
        except Exception as exc:
            last_error = exc

        if last_error is not None:
            raise last_error
        raise APIError("Failed to list memories")

    def chat(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Chat with MemOS using a non-streaming response route."""
        user_id = kwargs.get("user_id")
        if not user_id:
            raise APIError("Chat requires user_id")

        # Core API route from the official /api_docs/chat/chat documentation.
        simple_payload: dict[str, Any] = {
            "user_id": user_id,
            "query": query,
        }
        conversation_id = kwargs.get("conversation_id")
        if conversation_id is not None:
            simple_payload["conversation_id"] = conversation_id
        try:
            data = self.transport.request_json("POST", "/chat", json_body=simple_payload)
            return normalize_chat_response(data, original_query=query)
        except Exception as simple_error:
            last_error: Exception | None = simple_error

        # Product API route from the newer /api-reference/chat-with-memos-(complete-response)
        # documentation. Keep it as a compatibility fallback.
        payload: dict[str, Any] = {
            "user_id": user_id,
            "query": query,
        }
        field_map = {
            "conversation_id": "session_id",
            "agent_id": "agent_id",
            "app_id": "app_id",
            "run_id": "run_id",
            "mode": "mode",
            "system_prompt": "system_prompt",
            "top_k": "top_k",
            "pref_top_k": "pref_top_k",
            "model_name_or_path": "model_name_or_path",
            "max_tokens": "max_tokens",
            "temperature": "temperature",
            "top_p": "top_p",
            "internet_search": "internet_search",
            "include_preference": "include_preference",
            "add_message_on_answer": "add_message_on_answer",
            "mem_cube_id": "mem_cube_id",
            "readable_cube_ids": "readable_cube_ids",
            "writable_cube_ids": "writable_cube_ids",
            "history": "history",
            "filter": "filter",
            "threshold": "threshold",
            "moscube": "moscube",
        }
        for source_field, payload_field in field_map.items():
            value = kwargs.get(source_field)
            if value is not None:
                payload[payload_field] = value

        try:
            data = self.transport.request_first_json(
                "POST",
                [
                    "/product/chat/complete",
                    "/chat/complete",
                ],
                json_body=payload,
            )
            return normalize_chat_response(data, original_query=query)
        except Exception as exc:
            last_error = exc

        if last_error is not None:
            raise last_error
        raise APIError("Failed to chat with MemOS")

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

    def get_memory(self, memory_id: str, **kwargs: Any) -> dict[str, Any]:
        """Get a specific memory."""
        user_id = kwargs.get("user_id")
        last_error: Exception | None = None

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

    def delete_memory(self, memory_id: str, **kwargs: Any) -> dict[str, Any]:
        """Delete a specific memory."""
        resolved_memory_id = memory_id
        if memory_id and len(memory_id) < 36:
            try:
                resolved_memory = self.get_memory(memory_id, user_id=kwargs.get("user_id"))
                resolved_memory_id = str(resolved_memory.get("id") or memory_id)
            except Exception:
                resolved_memory_id = memory_id

        data = self.transport.request_json(
            "POST",
            "/delete/memory",
            json_body={"memory_ids": [resolved_memory_id]},
        )
        return normalize_delete_response(data, resolved_memory_id)
