"""Tests for the client-side sync-wait wired into `memos add`."""
from __future__ import annotations

import io
import logging
import unittest
from unittest.mock import patch

import typer
from rich.console import Console

from memos_cli.commands import memory, memory_cmd
from memos_cli.commands.memory_cmd import (
    _TERMINAL_TASK_STATUSES,
    _extract_status,
    _extract_task_id,
    _poll_task_status,
)
from memos_cli.config import MemOSConfig, PlatformConfig
from memos_cli.main import app
from memos_cli.output import (
    _build_add_success_context,
    _build_agent_payload,
    format_add_result,
)


def _make_console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, no_color=True, width=200)
    return console, buffer


class FakeBackend:
    """Simulates the MemOS backend `add_memory` + `get_status` contract."""

    def __init__(
        self,
        *,
        add_response: dict,
        status_sequence: list[dict] | None = None,
        status_error_after: int | None = None,
    ) -> None:
        self._add_response = add_response
        self._status_sequence = list(status_sequence or [])
        self.add_calls: list[dict] = []
        self.status_calls: list[str] = []
        self._status_error_after = status_error_after

    def add_memory(self, messages, **kwargs):
        self.add_calls.append({"messages": messages, **kwargs})
        return self._add_response

    def get_status(self, task_id):
        self.status_calls.append(task_id)
        if (
            self._status_error_after is not None
            and len(self.status_calls) > self._status_error_after
        ):
            raise RuntimeError("simulated transport failure")
        if not self._status_sequence:
            return {"data": {"status": "completed"}}
        return self._status_sequence.pop(0)


class ExtractHelpersTests(unittest.TestCase):
    def test_extract_task_id_from_data_task_id(self) -> None:
        result = {"data": {"task_id": "task-1", "status": "running"}}
        self.assertEqual(_extract_task_id(result), "task-1")

    def test_extract_task_id_from_data_taskid_camelcase(self) -> None:
        result = {"data": {"taskId": "task-2"}}
        self.assertEqual(_extract_task_id(result), "task-2")

    def test_extract_task_id_from_top_level(self) -> None:
        self.assertEqual(_extract_task_id({"task_id": "task-3"}), "task-3")
        self.assertEqual(_extract_task_id({"taskId": "task-4"}), "task-4")

    def test_extract_task_id_missing_or_wrong_type(self) -> None:
        self.assertIsNone(_extract_task_id({}))
        self.assertIsNone(_extract_task_id({"data": {}}))
        self.assertIsNone(_extract_task_id({"data": {"task_id": ""}}))
        self.assertIsNone(_extract_task_id({"data": {"task_id": None}}))
        self.assertIsNone(_extract_task_id(None))
        self.assertIsNone(_extract_task_id("not a dict"))

    def test_extract_status_normalizes_case_and_shape(self) -> None:
        self.assertEqual(_extract_status({"data": {"status": "RUNNING"}}), "running")
        self.assertEqual(_extract_status({"data": {"status": "  Completed  "}}), "completed")
        self.assertEqual(_extract_status({"status": "failed"}), "failed")
        self.assertEqual(_extract_status({}), "")
        self.assertEqual(_extract_status(None), "")

    def test_terminal_status_set(self) -> None:
        self.assertIn("completed", _TERMINAL_TASK_STATUSES)
        self.assertIn("failed", _TERMINAL_TASK_STATUSES)
        self.assertNotIn("running", _TERMINAL_TASK_STATUSES)


class PollTaskStatusTests(unittest.TestCase):
    def test_poll_returns_on_terminal_status(self) -> None:
        backend = FakeBackend(
            add_response={},
            status_sequence=[
                {"data": {"status": "running"}},
                {"data": {"status": "completed"}},
            ],
        )
        with patch.object(memory_cmd.time, "sleep") as sleep_mock:
            result = _poll_task_status(backend, "task-x", timeout=5.0, poll_interval=0.0)
        self.assertEqual(_extract_status(result), "completed")
        self.assertEqual(len(backend.status_calls), 2)
        sleep_mock.assert_called()

    def test_poll_stops_immediately_when_first_call_is_terminal(self) -> None:
        backend = FakeBackend(
            add_response={},
            status_sequence=[{"data": {"status": "completed"}}],
        )
        with patch.object(memory_cmd.time, "sleep") as sleep_mock:
            result = _poll_task_status(backend, "task-x", timeout=5.0, poll_interval=0.0)
        self.assertEqual(_extract_status(result), "completed")
        self.assertEqual(len(backend.status_calls), 1)
        sleep_mock.assert_not_called()

    def test_poll_respects_timeout(self) -> None:
        backend = FakeBackend(
            add_response={},
            status_sequence=[{"data": {"status": "running"}}] * 50,
        )

        clock = [1000.0]

        def fake_time():
            return clock[0]

        def fake_sleep(_seconds):
            clock[0] += 0.5

        with patch.object(memory_cmd.time, "time", side_effect=fake_time):
            with patch.object(memory_cmd.time, "sleep", side_effect=fake_sleep):
                result = _poll_task_status(
                    backend, "task-x", timeout=1.0, poll_interval=0.5
                )
        # Timed out with last observed status still "running"
        self.assertEqual(_extract_status(result), "running")
        # Deadline was ~1s, so the loop shouldn't have made unbounded calls.
        self.assertLessEqual(len(backend.status_calls), 5)

    def test_poll_zero_timeout_makes_no_status_call(self) -> None:
        backend = FakeBackend(
            add_response={},
            status_sequence=[{"data": {"status": "running"}}],
        )
        with patch.object(memory_cmd.time, "sleep") as sleep_mock:
            result = _poll_task_status(backend, "task-x", timeout=0.0, poll_interval=0.0)
        self.assertEqual(result, {})
        self.assertEqual(backend.status_calls, [])
        sleep_mock.assert_not_called()

    def test_poll_aborts_on_transport_error(self) -> None:
        backend = FakeBackend(
            add_response={},
            status_sequence=[
                {"data": {"status": "running"}},
            ],
            status_error_after=1,
        )
        with patch.object(memory_cmd.time, "sleep"):
            result = _poll_task_status(backend, "task-x", timeout=5.0, poll_interval=0.0)
        # First call returns "running", second call raises — loop exits with the last observed payload.
        self.assertEqual(_extract_status(result), "running")
        self.assertEqual(len(backend.status_calls), 2)

    def test_poll_logs_transport_error_at_warning(self) -> None:
        backend = FakeBackend(
            add_response={},
            status_sequence=[],
            status_error_after=0,
        )
        with patch.object(memory_cmd.time, "sleep"):
            with self.assertLogs(memory_cmd.logger, level=logging.WARNING) as caplog:
                result = _poll_task_status(
                    backend, "task-x", timeout=5.0, poll_interval=0.0
                )
        # Even with no successful observation the loop returns cleanly, but
        # the underlying failure is surfaced through the logger so a broken
        # /get/status endpoint (or a programming error in the backend client)
        # stays diagnosable instead of turning into a silent empty payload.
        self.assertEqual(result, {})
        self.assertTrue(
            any("get_status(task-x) failed" in message for message in caplog.output),
            caplog.output,
        )


class CmdAddPollingTests(unittest.TestCase):
    def _config(self) -> MemOSConfig:
        config = MemOSConfig(
            platform=PlatformConfig(api_key="k", base_url="https://example.test/api")
        )
        config.defaults.user_id = "user_1"
        config.defaults.conversation_id = "conv_1"
        return config

    def test_cmd_add_polls_when_wait_and_task_id_present(self) -> None:
        backend = FakeBackend(
            add_response={
                "code": 0,
                "message": "add accepted",
                "data": {"task_id": "task-42", "status": "running"},
            },
            status_sequence=[
                {"data": {"status": "running"}},
                {"data": {"status": "completed"}},
            ],
        )
        captured: dict = {}

        def fake_format(_console, **kwargs):
            captured.update(kwargs)

        with patch.object(memory_cmd, "_load_backend", return_value=(self._config(), backend)):
            with patch.object(memory_cmd, "format_agent_envelope", side_effect=fake_format):
                with patch.object(memory_cmd.time, "sleep"):
                    memory_cmd.cmd_add(
                        message_text="hello",
                        message_option=None,
                        user_id=None,
                        agent_id=None,
                        app_id=None,
                        conversation_id=None,
                        tags_json=None,
                        info_json=None,
                        allow_public=None,
                        allow_knowledgebase_ids=None,
                        async_mode=None,
                        output_format="agent",
                        detail="simple",
                        wait=True,
                        wait_timeout=5.0,
                    )

        self.assertEqual(backend.status_calls, ["task-42", "task-42"])
        self.assertEqual(captured["task_id"], "task-42")
        self.assertEqual(captured["final_status"], "completed")
        self.assertTrue(captured["waited"])

    def test_cmd_add_skips_polling_when_no_wait(self) -> None:
        backend = FakeBackend(
            add_response={
                "code": 0,
                "message": "add accepted",
                "data": {"task_id": "task-42", "status": "running"},
            },
        )
        captured: dict = {}

        def fake_format(_console, **kwargs):
            captured.update(kwargs)

        with patch.object(memory_cmd, "_load_backend", return_value=(self._config(), backend)):
            with patch.object(memory_cmd, "format_agent_envelope", side_effect=fake_format):
                memory_cmd.cmd_add(
                    message_text="hello",
                    message_option=None,
                    user_id=None,
                    agent_id=None,
                    app_id=None,
                    conversation_id=None,
                    tags_json=None,
                    info_json=None,
                    allow_public=None,
                    allow_knowledgebase_ids=None,
                    async_mode=None,
                    output_format="agent",
                    detail="simple",
                    wait=False,
                    wait_timeout=5.0,
                )

        self.assertEqual(backend.status_calls, [])
        self.assertEqual(captured["task_id"], "task-42")
        self.assertEqual(captured["final_status"], "running")
        self.assertFalse(captured["waited"])

    def test_cmd_add_no_polling_when_task_id_missing(self) -> None:
        backend = FakeBackend(
            add_response={"code": 0, "message": "Memory added", "data": {}},
        )
        captured: dict = {}

        def fake_format(_console, **kwargs):
            captured.update(kwargs)

        with patch.object(memory_cmd, "_load_backend", return_value=(self._config(), backend)):
            with patch.object(memory_cmd, "format_agent_envelope", side_effect=fake_format):
                memory_cmd.cmd_add(
                    message_text="hello",
                    message_option=None,
                    user_id=None,
                    agent_id=None,
                    app_id=None,
                    conversation_id=None,
                    tags_json=None,
                    info_json=None,
                    allow_public=None,
                    allow_knowledgebase_ids=None,
                    async_mode=None,
                    output_format="agent",
                    detail="simple",
                    wait=True,
                    wait_timeout=5.0,
                )

        self.assertEqual(backend.status_calls, [])
        self.assertIsNone(captured["task_id"])

    def test_cmd_add_no_polling_when_already_completed(self) -> None:
        """If the add response is already terminal, skip the poll — no need to call /get/status."""
        backend = FakeBackend(
            add_response={
                "code": 0,
                "data": {"task_id": "task-completed", "status": "completed"},
            },
        )
        captured: dict = {}

        def fake_format(_console, **kwargs):
            captured.update(kwargs)

        with patch.object(memory_cmd, "_load_backend", return_value=(self._config(), backend)):
            with patch.object(memory_cmd, "format_agent_envelope", side_effect=fake_format):
                memory_cmd.cmd_add(
                    message_text="hello",
                    message_option=None,
                    user_id=None,
                    agent_id=None,
                    app_id=None,
                    conversation_id=None,
                    tags_json=None,
                    info_json=None,
                    allow_public=None,
                    allow_knowledgebase_ids=None,
                    async_mode=None,
                    output_format="agent",
                    detail="simple",
                    wait=True,
                    wait_timeout=5.0,
                )

        self.assertEqual(backend.status_calls, [])
        self.assertEqual(captured["final_status"], "completed")

    def test_cmd_add_wait_true_but_zero_timeout_is_treated_as_no_wait(self) -> None:
        """wait=True + wait_timeout=0 previously produced zero polls yet reported waited=True.

        Guard the poll invocation so a non-positive timeout is treated as an explicit opt-out
        of waiting: no /get/status calls, and the envelope reports waited=False so downstream
        consumers can distinguish 'fire and forget' from 'waited to completion'.
        """
        backend = FakeBackend(
            add_response={
                "code": 0,
                "data": {"task_id": "task-42", "status": "running"},
            },
        )
        captured: dict = {}

        def fake_format(_console, **kwargs):
            captured.update(kwargs)

        with patch.object(memory_cmd, "_load_backend", return_value=(self._config(), backend)):
            with patch.object(memory_cmd, "format_agent_envelope", side_effect=fake_format):
                memory_cmd.cmd_add(
                    message_text="hello",
                    message_option=None,
                    user_id=None,
                    agent_id=None,
                    app_id=None,
                    conversation_id=None,
                    tags_json=None,
                    info_json=None,
                    allow_public=None,
                    allow_knowledgebase_ids=None,
                    async_mode=None,
                    output_format="agent",
                    detail="simple",
                    wait=True,
                    wait_timeout=0.0,
                )

        self.assertEqual(backend.status_calls, [])
        self.assertEqual(captured["final_status"], "running")
        self.assertFalse(captured["waited"])


class AddTyperEntrypointTests(unittest.TestCase):
    def test_add_forwards_wait_defaults(self) -> None:
        with patch.object(memory, "cmd_add") as cmd_add:
            memory.add(
                "hello",
                message_option=None,
                user_id=None,
                output_format="agent",
                wait=True,
                wait_timeout=30.0,
            )
        self.assertEqual(cmd_add.call_count, 1)
        kwargs = cmd_add.call_args.kwargs
        self.assertTrue(kwargs["wait"])
        self.assertEqual(kwargs["wait_timeout"], 30.0)
        self.assertEqual(kwargs["message_text"], "hello")

    def test_add_forwards_no_wait_override(self) -> None:
        with patch.object(memory, "cmd_add") as cmd_add:
            memory.add(
                "hello",
                message_option=None,
                user_id=None,
                output_format="agent",
                wait=False,
                wait_timeout=5.5,
            )
        kwargs = cmd_add.call_args.kwargs
        self.assertFalse(kwargs["wait"])
        self.assertEqual(kwargs["wait_timeout"], 5.5)


class MemosListAliasTests(unittest.TestCase):
    def _registered_names(self) -> list[str]:
        names: list[str] = []
        for command in app.registered_commands:
            if command.name:
                names.append(command.name)
            elif command.callback is not None:
                names.append(command.callback.__name__)
        return names

    def test_list_command_registered(self) -> None:
        names = self._registered_names()
        self.assertIn("list", names)
        self.assertIn("get", names)

    def test_list_and_get_share_the_same_callback(self) -> None:
        list_cmd = next((c for c in app.registered_commands if c.name == "list"), None)
        get_cmd = next(
            (
                c
                for c in app.registered_commands
                if c.callback is not None and c.callback.__name__ == "get" and c.name is None
            ),
            None,
        )
        self.assertIsNotNone(list_cmd, "memos list command not registered")
        self.assertIsNotNone(get_cmd, "memos get command not registered")
        self.assertIs(list_cmd.callback, get_cmd.callback)


class FormatAddResultTests(unittest.TestCase):
    def test_task_completed_prints_success_with_task_id(self) -> None:
        console, buffer = _make_console()
        format_add_result(
            console,
            {"data": {"task_id": "task-42", "status": "completed"}},
            output="text",
            task_id="task-42",
            final_status="completed",
            waited=True,
        )
        out = buffer.getvalue()
        self.assertIn("Memory added", out)
        self.assertIn("task-42", out)

    def test_task_running_after_wait_prints_processing_hint(self) -> None:
        console, buffer = _make_console()
        format_add_result(
            console,
            {"data": {"task_id": "task-42", "status": "running"}},
            output="text",
            task_id="task-42",
            final_status="running",
            waited=True,
        )
        out = buffer.getvalue()
        self.assertIn("still processing", out)
        self.assertIn("task-42", out)
        self.assertIn("memos status", out)

    def test_task_running_no_wait_prints_accepted_hint(self) -> None:
        console, buffer = _make_console()
        format_add_result(
            console,
            {"data": {"task_id": "task-42", "status": "running"}},
            output="text",
            task_id="task-42",
            final_status="running",
            waited=False,
        )
        out = buffer.getvalue()
        self.assertIn("accepted", out)
        self.assertIn("task-42", out)
        self.assertIn("--wait", out)

    def test_task_failed_prints_failure(self) -> None:
        console, buffer = _make_console()
        format_add_result(
            console,
            {"data": {"task_id": "task-42", "status": "failed"}},
            output="text",
            task_id="task-42",
            final_status="failed",
            waited=True,
        )
        out = buffer.getvalue()
        self.assertIn("failed", out.lower())
        self.assertIn("task-42", out)

    def test_no_task_id_falls_back_to_legacy_branch(self) -> None:
        console, buffer = _make_console()
        format_add_result(
            console,
            {"data": {}, "message": "Memory added"},
            output="text",
        )
        out = buffer.getvalue()
        self.assertIn("Memory added", out)


class AddSuccessContextTests(unittest.TestCase):
    def test_context_completed_reads_success(self) -> None:
        block = _build_add_success_context(
            message="add accepted",
            detail="simple",
            task_id="task-1",
            final_status="completed",
            waited=True,
        )
        self.assertIn("Add success", block)
        self.assertIn("task_id: task-1", block)
        self.assertIn("status: completed", block)

    def test_context_running_after_timeout(self) -> None:
        block = _build_add_success_context(
            message="add accepted",
            detail="simple",
            task_id="task-1",
            final_status="running",
            waited=True,
        )
        self.assertIn("still processing", block)
        self.assertIn("hint", block)

    def test_context_failed(self) -> None:
        block = _build_add_success_context(
            message="",
            detail="simple",
            task_id="task-1",
            final_status="failed",
            waited=True,
        )
        self.assertIn("Add failed", block)

    def test_context_failed_does_not_recommend_polling(self) -> None:
        """A terminal-failure status should not suggest polling the (dead) task."""
        block = _build_add_success_context(
            message="",
            detail="simple",
            task_id="task-1",
            final_status="failed",
            waited=True,
        )
        self.assertNotIn("hint", block)
        self.assertNotIn("memos status task-1", block)

    def test_context_error_does_not_recommend_polling(self) -> None:
        block = _build_add_success_context(
            message="",
            detail="simple",
            task_id="task-1",
            final_status="error",
            waited=True,
        )
        self.assertNotIn("hint", block)

    def test_context_backwards_compatible_no_task_id(self) -> None:
        block = _build_add_success_context(message="Memory added", detail="simple")
        self.assertIn("Add success", block)
        self.assertNotIn("task_id", block)


class FormatAddResultBranchTests(unittest.TestCase):
    """Cover the merged success branch in format_add_result."""

    def test_success_status_variants_all_print_success_line(self) -> None:
        for status in ("completed", "success", "succeeded", "done"):
            with self.subTest(status=status):
                console, buffer = _make_console()
                format_add_result(
                    console,
                    {"data": {"task_id": "task-42", "status": status}},
                    output="text",
                    task_id="task-42",
                    final_status=status,
                    waited=True,
                )
                out = buffer.getvalue()
                self.assertIn("✓", out)
                self.assertIn("Memory added", out)
                self.assertIn("task-42", out)


class AgentEnvelopeAddPayloadTests(unittest.TestCase):
    """`_build_agent_payload("add", ...)` must round-trip `waited` in its
    returned dict so downstream consumers can distinguish "waited to
    completion" from "fired and forgotten" — symmetrical with task_id and
    final_status which are already serialised."""

    def _add_payload(self, *, waited: bool) -> dict:
        return _build_agent_payload(
            command="add",
            data={
                "code": 0,
                "message": "ok",
                "data": {"task_id": "task-1", "status": "completed"},
            },
            identity={"user_id": "u"},
            detail="simple",
            records_preformatted=False,
            warnings=[],
            task_id="task-1",
            final_status="completed",
            waited=waited,
        )

    def test_waited_true_is_serialised(self) -> None:
        payload = self._add_payload(waited=True)
        self.assertIn("waited", payload)
        self.assertTrue(payload["waited"])

    def test_waited_false_is_serialised(self) -> None:
        payload = self._add_payload(waited=False)
        self.assertIn("waited", payload)
        self.assertFalse(payload["waited"])


if __name__ == "__main__":
    unittest.main()
