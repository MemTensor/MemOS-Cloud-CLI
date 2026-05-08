"""Base backend interface for MemOS CLI."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BackendBase(ABC):
    """Abstract base class for backend implementations."""
    
    @abstractmethod
    def ping(self, timeout: float = 5.0) -> dict[str, Any]:
        """Ping the API to validate credentials."""
        pass
    
    @abstractmethod
    def add_memory(self, text: str, **kwargs) -> dict[str, Any]:
        """Add a new memory."""
        pass
    
    @abstractmethod
    def search_memories(self, query: str, **kwargs) -> list[dict[str, Any]]:
        """Search memories."""
        pass

    @abstractmethod
    def list_memories(self, **kwargs) -> list[dict[str, Any]]:
        """List memories."""
        pass

    @abstractmethod
    def chat(self, query: str, **kwargs) -> dict[str, Any]:
        """Chat with MemOS."""
        pass

    @abstractmethod
    def create_knowledgebase(self, name: str, description: str | None = None, **kwargs) -> dict[str, Any]:
        """Create a knowledge base."""
        pass

    @abstractmethod
    def add_knowledgebase_files(self, knowledgebase_id: str, files: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
        """Add files to a knowledge base."""
        pass
    
    @abstractmethod
    def get_memory(self, memory_id: str) -> dict[str, Any]:
        """Get a specific memory."""
        pass
    
    @abstractmethod
    def delete_memory(self, memory_id: str) -> dict[str, Any]:
        """Delete a memory."""
        pass
