from __future__ import annotations

import unittest
from unittest.mock import patch

from memos_cli.commands import memory, memory_cmd
from memos_cli.config import MemOSConfig, PlatformConfig
from memos_cli.output import extract_memory_records_from_response


class MemoryGetScopeTests(unittest.TestCase):
    """The get/list read path must use the same conversation scope as add."""

    def test_cmd_get_forwards_conversation_id_to_backend(self) -> None:
        config = MemOSConfig(
            platform=PlatformConfig(
                api_key="test-key",
                base_url="https://example.test/api",
            )
        )
        config.defaults.user_id = "user_1"
        config.defaults.conversation_id = "conversation_1"

        captured: dict = {}

        class Backend:
            def get_memories(self, **kwargs):
                captured.update(kwargs)
                return {"data": {"text_mem": []}}

        with patch.object(memory_cmd, "_load_backend", return_value=(config, Backend())):
            with patch.object(memory_cmd, "format_json"):
                memory_cmd.cmd_get(
                    user_id=None,
                    conversation_id=None,
                    page=1,
                    size=50,
                    include_preference=None,
                    include_tool_memory=None,
                    output_format="json",
                    detail="simple",
                )

        self.assertEqual(captured["user_id"], "user_1")
        self.assertEqual(captured["conversation_id"], "conversation_1")

    def test_cmd_get_prefers_explicit_conversation_id(self) -> None:
        config = MemOSConfig(
            platform=PlatformConfig(
                api_key="test-key",
                base_url="https://example.test/api",
            )
        )
        config.defaults.user_id = "user_1"
        config.defaults.conversation_id = "conversation_1"

        captured: dict = {}

        class Backend:
            def get_memories(self, **kwargs):
                captured.update(kwargs)
                return {"data": {"text_mem": []}}

        with patch.object(memory_cmd, "_load_backend", return_value=(config, Backend())):
            with patch.object(memory_cmd, "format_json"):
                memory_cmd.cmd_get(
                    user_id="user_2",
                    conversation_id="conv_explicit",
                    page=1,
                    size=50,
                    include_preference=None,
                    include_tool_memory=None,
                    output_format="json",
                    detail="simple",
                )

        self.assertEqual(captured["user_id"], "user_2")
        self.assertEqual(captured["conversation_id"], "conv_explicit")

    def test_get_entrypoint_passes_conversation_id(self) -> None:
        with patch.object(memory, "cmd_get") as cmd_get:
            memory.get(
                user_id_arg=None,
                user_id="user_1",
                conversation_id="conv_1",
                page=2,
                size=25,
                include_preference="true",
                include_tool_memory="false",
                output_format="json",
                detail="detail",
            )

        self.assertEqual(cmd_get.call_count, 1)
        self.assertEqual(cmd_get.call_args.kwargs["conversation_id"], "conv_1")
        self.assertEqual(cmd_get.call_args.kwargs["user_id"], "user_1")

    def test_list_entrypoint_delegates_to_cmd_get(self) -> None:
        with patch.object(memory, "cmd_get") as cmd_get:
            memory.list(
                user_id_arg="user_1",
                user_id=None,
                conversation_id="conv_1",
                page=1,
                size=10,
                include_preference=None,
                include_tool_memory=None,
                output_format="table",
                detail="simple",
            )

        self.assertEqual(cmd_get.call_count, 1)
        self.assertEqual(cmd_get.call_args.kwargs["conversation_id"], "conv_1")
        self.assertEqual(cmd_get.call_args.kwargs["user_id"], "user_1")


class GetMemoryTextMemParsingTests(unittest.TestCase):
    """list/get must not silently drop records served via the text_mem envelope."""

    def test_extract_records_reads_text_mem_bucket(self) -> None:
        response = {
            "code": 0,
            "data": {
                "text_mem": [
                    {
                        "session_id": "s1",
                        "conversation_id": "conv_1",
                        "memories": [
                            {"id": "mem_1", "memory": "User likes coffee"},
                            {"id": "mem_2", "text": "Deployment is at 3pm"},
                        ],
                    }
                ]
            },
        }

        records = extract_memory_records_from_response(response, detail="simple")

        self.assertEqual(len(records), 2)
        contents = {record.get("memory") for record in records}
        self.assertIn("User likes coffee", contents)
        self.assertIn("Deployment is at 3pm", contents)


if __name__ == "__main__":
    unittest.main()
