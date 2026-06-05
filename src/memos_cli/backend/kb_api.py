"""Knowledge Base API wrapper for MemOS backend."""
from __future__ import annotations

from typing import Any

from memos_cli.backend.transport import APIError, MemOSTransport


class KnowledgeBaseAPI:
    """Knowledge-base route orchestration."""

    def __init__(self, transport: MemOSTransport):
        self.transport = transport

    def create(self, name: str, description: str | None = None) -> dict[str, Any]:
        """Create a knowledge base."""
        if not name:
            raise APIError("knowledgebase_name is required")

        payload: dict[str, Any] = {"knowledgebase_name": name}
        if description:
            payload["knowledgebase_description"] = description

        return self.transport.request_json(
            "POST", "/create/knowledgebase", json_body=payload
        )

    def remove(self, kb_id: str) -> dict[str, Any]:
        """Remove (delete) a knowledge base."""
        if not kb_id:
            raise APIError("knowledgebase_id is required")

        payload: dict[str, Any] = {"knowledgebase_id": kb_id}
        return self.transport.request_json(
            "POST", "/delete/knowledgebase", json_body=payload
        )

    def add_file(self, kb_id: str, files: list[dict[str, str]]) -> dict[str, Any]:
        """Upload documents to a knowledge base.

        Each file entry should be {"content": "<url_or_base64>"}.
        """
        if not kb_id:
            raise APIError("knowledgebase_id is required")
        if not files:
            raise APIError("At least one file is required")

        payload: dict[str, Any] = {
            "knowledgebase_id": kb_id,
            "file": files,
        }
        return self.transport.request_json(
            "POST", "/add/knowledgebase-file", json_body=payload
        )

    def get_file(self, file_ids: list[str]) -> dict[str, Any]:
        """Get knowledge base file details and processing status."""
        if not file_ids:
            raise APIError("file_ids is required")

        payload: dict[str, Any] = {"file_ids": file_ids}
        return self.transport.request_json(
            "POST", "/get/knowledgebase-file", json_body=payload
        )

    def list_files(
        self,
        kb_id: str,
        *,
        file_type: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """List files in a knowledge base with pagination."""
        if not kb_id:
            raise APIError("knowledgebase_id is required")

        payload: dict[str, Any] = {
            "knowledgebase_id": kb_id,
            "page": page,
            "page_size": page_size,
        }
        if file_type:
            payload["type"] = file_type

        return self.transport.request_json(
            "POST", "/get/knowledgebase-file", json_body=payload
        )

    def delete_file(self, kb_id: str, file_ids: list[str]) -> dict[str, Any]:
        """Delete files from a knowledge base."""
        if not kb_id:
            raise APIError("knowledgebase_id is required")
        if not file_ids:
            raise APIError("file_ids is required")

        payload: dict[str, Any] = {
            "knowledgebase_id": kb_id,
            "file_ids": file_ids,
        }
        return self.transport.request_json(
            "POST", "/delete/knowledgebase-file", json_body=payload
        )
