"""Message-domain API wrapper for MemOS backend."""
from __future__ import annotations

from typing import Any

from memos_cli.backend.transport import APIError, MemOSTransport


class MessageAPI:
    """Message-specific route orchestration."""

    def __init__(self, transport: MemOSTransport):
        self.transport = transport

    def get_message(
        self,
        user_id: str,
        conversation_id: str,
        *,
        limit: int = 6,
    ) -> dict[str, Any]:
        """Retrieve original conversation messages."""
        if not user_id:
            raise APIError("user_id is required for get_message")
        if not conversation_id:
            raise APIError("conversation_id is required for get_message")

        payload: dict[str, Any] = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "message_limit_number": min(limit, 50),
        }
        return self.transport.request_json("POST", "/get/message", json_body=payload)

    def get_status(self, task_id: str) -> dict[str, Any]:
        """Query async task status (running/completed/failed)."""
        if not task_id:
            raise APIError("task_id is required for get_status")

        payload: dict[str, Any] = {"task_id": task_id}
        return self.transport.request_json("POST", "/get/status", json_body=payload)
