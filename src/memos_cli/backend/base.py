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
    def add_memory(self, messages: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
        """Add messages."""
        pass

    @abstractmethod
    def add_feedback(self, feedback_content: str, **kwargs) -> dict[str, Any]:
        """Add feedback / summary content."""
        pass

    @abstractmethod
    def extract_memory(self, messages: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
        """Extract memory candidates without storing them."""
        pass
    
    @abstractmethod
    def rerank_documents(self, query: str, documents: list[str], **kwargs) -> dict[str, Any]:
        """Rerank candidate documents for a query."""
        pass

    @abstractmethod
    def search_memories(self, query: str, **kwargs) -> dict[str, Any]:
        """Search memories."""
        pass

    @abstractmethod
    def get_memories(self, **kwargs) -> dict[str, Any]:
        """Get memories."""
        pass

    @abstractmethod
    def chat(self, query: str, **kwargs) -> dict[str, Any]:
        """Chat with MemOS."""
        pass
    
    @abstractmethod
    def get_memory(self, memory_id: str) -> dict[str, Any]:
        """Get a specific memory."""
        pass

    @abstractmethod
    def get_memory_origin(self, memory_id: str) -> dict[str, Any]:
        """Get the origin/source payload for a specific memory."""
        pass
    
    @abstractmethod
    def delete_memory(self, memory_ids: list[str], **kwargs) -> dict[str, Any]:
        """Delete memories."""
        pass
