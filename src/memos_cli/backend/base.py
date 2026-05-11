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
    def add_feedback(self, feedback_content: str, **kwargs) -> dict[str, Any]:
        """Add feedback / summary content."""
        pass

    @abstractmethod
    def extract_memory(self, text: str, **kwargs) -> dict[str, Any]:
        """Extract memory candidates without storing them."""
        pass
    
    @abstractmethod
    def rerank_documents(self, query: str, documents: list[str], **kwargs) -> dict[str, Any]:
        """Rerank candidate documents for a query."""
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
    def list_knowledgebases(self, **kwargs) -> list[dict[str, Any]]:
        """List knowledge bases."""
        pass

    @abstractmethod
    def add_knowledgebase_files(self, knowledgebase_id: str, files: list[dict[str, Any]], **kwargs) -> dict[str, Any]:
        """Add files to a knowledge base."""
        pass

    @abstractmethod
    def get_knowledgebase_file(self, file_id: str, **kwargs) -> dict[str, Any]:
        """Get a knowledge base file/document."""
        pass

    @abstractmethod
    def delete_knowledgebase_files(
        self,
        file_ids: list[str],
        knowledgebase_id: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Delete files from a knowledge base."""
        pass

    @abstractmethod
    def delete_knowledgebase(self, knowledgebase_id: str, **kwargs) -> dict[str, Any]:
        """Delete a knowledge base."""
        pass
    
    @abstractmethod
    def get_memory(self, memory_id: str) -> dict[str, Any]:
        """Get a specific memory."""
        pass
    
    @abstractmethod
    def delete_memory(self, memory_id: str) -> dict[str, Any]:
        """Delete a memory."""
        pass
