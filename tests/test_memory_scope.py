"""Regression tests for user_id scope symmetry and the `list` alias.

Issue #34: `memos add` could store a memory without a user scope (the resolved
user_id was silently dropped when its value was None), while `memos get`/`search`
always filtered by user_id — so a just-added memory could not be read back.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import typer

from memos_cli.backend.memory_api import MemoryAPI
from memos_cli.backend.transport import APIError
from memos_cli.commands import memory, memory_cmd
from memos_cli.config import MemOSConfig, PlatformConfig


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def request_json(self, method: str, path: str, **kwargs):
        self.calls.append((method, path, kwargs))
        return {"code": 0, "data": {}}


class AddMemoryScopeTests(unittest.TestCase):
    def test_add_memory_always_includes_user_id_in_body(self) -> None:
        transport = RecordingTransport()
        api = MemoryAPI(transport)

        api.add_memory(
            [{"role": "user", "content": "loves green tea"}],
            user_id="user_7",
            conversation_id="conversation_1",
        )

        body = transport.calls[0][2]["json_body"]
        self.assertEqual(body["user_id"], "user_7")
        self.assertEqual(body["conversation_id"], "conversation_1")

    def test_add_memory_rejects_missing_user_id(self) -> None:
        api = MemoryAPI(RecordingTransport())

        with self.assertRaises(APIError) as raised:
            api.add_memory(
                [{"role": "user", "content": "loves green tea"}],
                user_id=None,
            )

        self.assertIn("Add memory requires user_id", str(raised.exception))

    def test_search_memories_drops_empty_string_scope(self) -> None:
        """search must treat "" the same way add/get do: reject as an unscoped read.

        add_memory and get_memories both raise on falsy user_id. Sending user_id=""
        to /search/memory would filter the server-side query by an empty scope and
        never return memories written under a real user, silently reproducing the
        invisible-scope bug #34 was meant to fix.
        """
        transport = RecordingTransport()
        api = MemoryAPI(transport)

        api.search_memories("greens", user_id="")

        body = transport.calls[0][2]["json_body"]
        self.assertNotIn("user_id", body)


class ResolveScopeTests(unittest.TestCase):
    def test_resolve_scope_uses_config_default_when_flag_absent(self) -> None:
        config = MemOSConfig(
            platform=PlatformConfig(api_key="test-key"),
        )
        config.defaults.user_id = "default_user"

        scope = memory_cmd.resolve_scope(
            config=config,
            user_id=None,
            agent_id=None,
            app_id=None,
            run_id=None,
        )

        self.assertEqual(scope["user_id"], "default_user")


class ListAliasTests(unittest.TestCase):
    def test_list_command_forwards_to_cmd_get_as_list(self) -> None:
        with patch.object(memory, "cmd_get") as cmd_get:
            memory.list(
                None,
                user_id="user_7",
                page=None,
                size=None,
                include_preference=None,
                include_tool_memory=None,
                output_format="table",
                detail="simple",
            )

        self.assertEqual(cmd_get.call_count, 1)
        self.assertEqual(cmd_get.call_args.kwargs["user_id"], "user_7")
        self.assertEqual(cmd_get.call_args.kwargs["command_name"], "list")

    def test_get_command_forwards_to_cmd_get_as_get(self) -> None:
        with patch.object(memory, "cmd_get") as cmd_get:
            memory.get(
                None,
                user_id="user_7",
                page=None,
                size=None,
                include_preference=None,
                include_tool_memory=None,
                output_format="table",
                detail="simple",
            )

        self.assertEqual(cmd_get.call_count, 1)
        self.assertEqual(cmd_get.call_args.kwargs["command_name"], "get")

    def test_main_registers_list_command(self) -> None:
        from memos_cli import main

        click_group = typer.main.get_command(main.app)
        self.assertIn("list", click_group.commands)

    def test_cmd_get_outputs_list_command_name_in_agent_mode(self) -> None:
        config = MemOSConfig(
            platform=PlatformConfig(
                api_key="test-key",
                base_url="https://example.test/api",
            )
        )
        config.defaults.user_id = "user_1"

        class Backend:
            def get_memories(self, **kwargs):
                return {"data": {"memory_detail_list": []}}

        captured: dict = {}

        def fake_envelope(console, **kwargs):
            captured.update(kwargs)

        with patch.object(memory_cmd, "_load_backend", return_value=(config, Backend())):
            with patch.object(memory_cmd, "format_agent_envelope", side_effect=fake_envelope):
                memory_cmd.cmd_get(
                    user_id=None,
                    page=None,
                    size=None,
                    include_preference=None,
                    include_tool_memory=None,
                    output_format="agent",
                    detail="simple",
                    command_name="list",
                )

        self.assertEqual(captured["command"], "list")


if __name__ == "__main__":
    unittest.main()
