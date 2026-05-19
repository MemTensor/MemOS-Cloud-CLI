"""MemOS Cloud API backend implementation."""
from __future__ import annotations

from typing import Any

from memos_cli.backend.base import BackendBase
from memos_cli.backend.memory_api import MemoryAPI
from memos_cli.backend.transport import APIError, AuthError, MemOSTransport
from memos_cli.config import MemOSConfig


class MemOSBackend(BackendBase):
    """MemOS backend orchestrating transport and memory-domain API wrappers."""

    def __init__(self, config: MemOSConfig):
        self.config = config
        self.transport = MemOSTransport(
            base_url=config.platform.base_url,
            api_key=config.platform.api_key,
        )
        self.memory_api = MemoryAPI(self.transport)

    def ping(self, timeout: float = 5.0) -> dict[str, Any]:
        """Ping the API to validate credentials."""
        return self.memory_api.ping(timeout=timeout)

    def add_memory(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Add messages."""
        return self.memory_api.add_memory(messages, **kwargs)

    def add_feedback(self, feedback_content: str, **kwargs: Any) -> dict[str, Any]:
        """Add feedback content."""
        return self.memory_api.add_feedback(feedback_content, **kwargs)

    def extract_memory(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Extract memory candidates without storing them."""
        return self.memory_api.extract_memory(messages, **kwargs)

    def rerank_documents(self, query: str, documents: list[str], **kwargs: Any) -> dict[str, Any]:
        """Rerank candidate documents for a query."""
        return self.memory_api.rerank_documents(query, documents, **kwargs)

    def search_memories(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Search memories."""
        return self.memory_api.search_memories(query, **kwargs)

    def get_memories(self, **kwargs: Any) -> dict[str, Any]:
        """Get memories."""
        return self.memory_api.get_memories(**kwargs)

    def chat(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Chat with MemOS."""
        return self.memory_api.chat(query, **kwargs)

    def get_memory(self, memory_id: str, **kwargs: Any) -> dict[str, Any]:
        """Get a specific memory."""
        return self.memory_api.get_memory(memory_id, **kwargs)

    def get_memory_origin(self, memory_id: str, **kwargs: Any) -> dict[str, Any]:
        """Get origin/source payload for a specific memory."""
        return self.memory_api.get_memory_origin(memory_id, **kwargs)

    def delete_memory(self, memory_ids: list[str], **kwargs: Any) -> dict[str, Any]:
        """Delete memories."""
        return self.memory_api.delete_memory(memory_ids, **kwargs)


def get_backend(config: MemOSConfig) -> MemOSBackend:
    """Factory function to get backend instance."""
    return MemOSBackend(config)
