from __future__ import annotations

import unittest
from unittest.mock import patch

from memos_cli.commands import memory, memory_cmd
from memos_cli.config import MemOSConfig, PlatformConfig


class MemorySearchOptionsTests(unittest.TestCase):
    def test_search_passes_knowledgebase_ids_to_execution_layer(self) -> None:
        with patch.object(memory, "cmd_search") as cmd_search:
            memory.search(
                "search query",
                query_option=None,
                user_id=None,
                memory_limit_number=None,
                include_preference=None,
                preference_limit_number=None,
                include_tool_memory=None,
                tool_memory_limit_number=None,
                include_skill_memory=None,
                skill_memory_limit_number=None,
                knowledgebase_ids='["kb_1","kb_2"]',
                output_format="json",
                detail="simple",
            )

        self.assertEqual(cmd_search.call_count, 1)
        self.assertEqual(cmd_search.call_args.kwargs["knowledgebase_ids"], '["kb_1","kb_2"]')
        self.assertEqual(cmd_search.call_args.kwargs["limit"], 9)

    def test_cmd_search_parses_knowledgebase_ids_json_for_backend(self) -> None:
        captured: dict = {}
        config = MemOSConfig(
            platform=PlatformConfig(
                api_key="test-key",
                base_url="https://example.test/api",
            )
        )
        config.defaults.user_id = "user_1"
        config.defaults.conversation_id = "conversation_1"

        class Backend:
            def search_memories(self, query: str, **kwargs):
                captured["query"] = query
                captured.update(kwargs)
                return {"data": []}

        with patch.object(memory_cmd, "_load_backend", return_value=(config, Backend())):
            with patch.object(memory_cmd, "format_json"):
                memory_cmd.cmd_search(
                    "search query",
                    query_option=None,
                    user_id=None,
                    conversation_id=None,
                    filter_json=None,
                    knowledgebase_ids='["kb_1","kb_2"]',
                    limit=9,
                    include_preference=None,
                    preference_limit=9,
                    include_tool_memory=None,
                    tool_memory_limit=6,
                    include_skill=None,
                    skill_limit=6,
                    relativity=None,
                    output_format="json",
                    detail="simple",
                )

        self.assertEqual(captured["query"], "search query")
        self.assertEqual(captured["knowledgebase_ids"], ["kb_1", "kb_2"])


if __name__ == "__main__":
    unittest.main()
