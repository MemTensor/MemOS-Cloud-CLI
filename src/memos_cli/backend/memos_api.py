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

    def add_memory(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Add a new memory."""
        return self.memory_api.add_memory(text, **kwargs)

    def search_memories(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Search memories."""
        return self.memory_api.search_memories(query, **kwargs)

    def list_memories(self, **kwargs: Any) -> list[dict[str, Any]]:
        """List memories."""
        return self.memory_api.list_memories(**kwargs)

    def chat(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """Chat with MemOS."""
        return self.memory_api.chat(query, **kwargs)

    def create_knowledgebase(self, name: str, description: str | None = None, **kwargs: Any) -> dict[str, Any]:
        """Create a knowledge base."""
        return self.memory_api.create_knowledgebase(name, description=description, **kwargs)

    def add_knowledgebase_files(self, knowledgebase_id: str, files: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        """Add files to a knowledge base."""
        return self.memory_api.add_knowledgebase_files(knowledgebase_id, files, **kwargs)

    def get_memory(self, memory_id: str, **kwargs: Any) -> dict[str, Any]:
        """Get a specific memory."""
        return self.memory_api.get_memory(memory_id, **kwargs)

    def delete_memory(self, memory_id: str, **kwargs: Any) -> dict[str, Any]:
        """Delete a specific memory."""
        return self.memory_api.delete_memory(memory_id, **kwargs)


def get_backend(config: MemOSConfig) -> MemOSBackend:
    """Factory function to get backend instance."""
    return MemOSBackend(config)
