from __future__ import annotations

import io
import json
import os
import runpy
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from memos_cli.hooks.installer import HookConfigError, install_hook, is_managed_hook, uninstall_hook
from memos_cli.hooks.agents import get_hook_agent_spec, is_native_hook_agent
from memos_cli.hooks.runner import run_payload, run_stdin
from memos_cli.hooks.state_store import HookStateStore, HookTurnState


class FakeBackend:
    def __init__(self, result=None):
        self.result = result or {"results": [{"id": "m1", "memory": "prefers tests"}]}
        self.search_calls = []
        self.add_calls = []

    def search_memories(self, query, **kwargs):
        self.search_calls.append((query, kwargs))
        return self.result

    def add_memory(self, messages, **kwargs):
        self.add_calls.append((messages, kwargs))
        return {"ok": True}


def config(*, multi_view_enabled=False, agent_id=None):
    return SimpleNamespace(
        defaults=SimpleNamespace(
            user_id="test-user",
            framework=None,
            agent_id=agent_id,
            multi_view_enabled=multi_view_enabled,
        )
    )


def test_prompt_searches_saves_state_and_returns_context(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")

    result = run_payload(
        {"hook_event_name": "UserPromptSubmit", "sessionId": "s1", "prompt": "remember this"},
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    assert result["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "prefers tests" in result["hookSpecificOutput"]["additionalContext"]
    assert backend.search_calls[0][0] == "remember this"
    assert backend.search_calls[0][1] == {"user_id": "test-user", "conversation_id": "codex:s1"}
    state = store.load("s1")
    assert state is not None
    assert state.conversation_id == "codex:s1"
    assert state.prompt == "remember this"


def test_cursor_hook_uses_same_runner_with_cursor_lifecycle(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")

    result = run_payload(
        {
            "conversation_id": "s1",
            "generation_id": "g1",
            "prompt": "remember this",
            "hook_event_name": "beforeSubmitPrompt",
        },
        agent="cursor",
        fallback_event="beforeSubmitPrompt",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    assert result == {"continue": True}
    assert backend.search_calls == []
    state = store.load("s1", "g1")
    assert state is not None
    assert state.prompt == "remember this"

    # Cursor's stop event is not the response-complete event and must not
    # create a second add path.
    run_payload(
        {
            "conversation_id": "s1",
            "generation_id": "g1",
            "hook_event_name": "Stop",
            "text": "用户: remember this 助手: cursor answer",
        },
        agent="cursor",
        fallback_event="Stop",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert backend.add_calls == []

    result = run_payload(
        {
            "conversation_id": "s1",
            "generation_id": "g1",
            "hook_event_name": "afterAgentResponse",
            "text": "cursor answer",
        },
        agent="cursor",
        fallback_event="afterAgentResponse",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    assert result == {"continue": True}
    assert backend.add_calls == [(
        [{"role": "user", "content": "remember this"}, {"role": "assistant", "content": "cursor answer"}],
        {"user_id": "test-user", "conversation_id": "cursor:s1", "async_mode": True},
    )]

    # Cursor may deliver the same afterAgentResponse through merged hook
    # sources. A second payload has no prompt state and must be ignored,
    # rather than treating its assistant text as a new user prompt.
    run_payload(
        {
            "conversation_id": "s1",
            "generation_id": "g1",
            "hook_event_name": "afterAgentResponse",
            "text": "cursor answer",
        },
        agent="cursor",
        fallback_event="afterAgentResponse",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert len(backend.add_calls) == 1


def test_cline_duplicate_completion_is_ignored_after_state_is_consumed(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")

    run_payload(
        {
            "hookName": "UserPromptSubmit",
            "taskId": "cline-task-1",
            "userPromptSubmit": {"prompt": "cline question"},
        },
        agent="cline",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    completion = {
        "hookName": "TaskComplete",
        "taskId": "cline-task-1",
        "taskComplete": {"taskMetadata": {"result": "cline answer"}},
    }
    run_payload(
        completion,
        agent="cline",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    # A second Cline surface (or a retry after the plugin timeout) must not
    # fall back to extracting prompt text and submit the same turn again.
    run_payload(
        completion,
        agent="cline",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert len(backend.add_calls) == 1


def test_state_store_consume_claims_once(tmp_path):
    store = HookStateStore(tmp_path / "state")
    store.save(HookTurnState.create(session_key="s1", conversation_id="codex:s1", prompt="q"))

    assert store.consume("s1") is not None
    assert store.consume("s1") is None
    assert store.load("s1") is None


@pytest.mark.parametrize(
    ("agent", "payload", "expected_key"),
    [
        (
            "copilot",
            {
                "hook_event_name": "userPromptTransformed",
                "sessionId": "s1",
                "prompt": "remember this",
                "transformedPrompt": "remember this",
            },
            "modifiedTransformedPrompt",
        ),
        (
            "hermes",
            {
                "hook_event_name": "pre_llm_call",
                "session_id": "s1",
                "extra": {
                    "user_message": "remember this",
                    "conversation_history": [],
                    "is_first_turn": True,
                    "model": "gpt-4",
                    "platform": "cli",
                },
            },
            "context",
        ),
        (
            "antigravity",
            {"hook_event_name": "PreInvocation", "sessionId": "s1", "prompt": "remember this"},
            "injectSteps",
        ),
        (
            "openclaw",
            {"hook_event_name": "before_prompt_build", "sessionId": "s1", "prompt": "remember this"},
            "prependContext",
        ),
        (
            "cline",
            {
                "hookName": "UserPromptSubmit",
                "taskId": "s1",
                "userPromptSubmit": {"prompt": "remember this", "attachments": []},
            },
            "contextModification",
        ),
    ],
)
def test_added_agents_use_the_expected_search_response_shape(tmp_path, agent, payload, expected_key):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")

    result = run_payload(
        payload,
        agent=agent,
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    if expected_key == "modifiedTransformedPrompt":
        assert expected_key in result
        assert "prefers tests" in result[expected_key]
        assert "remember this" in result[expected_key]
    elif expected_key == "context":
        assert result[expected_key].startswith("<memos_memory_context")
        assert "prefers tests" in result[expected_key]
    elif expected_key == "prependContext":
        assert result[expected_key].startswith("<memos_memory_context")
        assert "prefers tests" in result[expected_key]
    elif expected_key == "injectSteps":
        assert result[expected_key][0]["ephemeralMessage"].startswith("<memos_memory_context")
        assert "prefers tests" in result[expected_key][0]["ephemeralMessage"]
    else:
        assert result["cancel"] is False
        assert "prefers tests" in result[expected_key]
    assert backend.search_calls


def test_cline_ide_nested_payload_supports_search_and_add(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")

    search_result = run_payload(
        {
            "clineVersion": "3.0.0",
            "hookName": "UserPromptSubmit",
            "taskId": "task-1",
            "workspaceRoots": [str(tmp_path)],
            "userPromptSubmit": {"prompt": "current question", "attachments": []},
        },
        agent="cline",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    assert search_result["cancel"] is False
    assert "prefers tests" in search_result["contextModification"]
    assert backend.search_calls == [(
        "current question",
        {"user_id": "test-user", "conversation_id": "cline:task-1"},
    )]

    add_result = run_payload(
        {
            "clineVersion": "3.0.0",
            "hookName": "TaskComplete",
            "taskId": "task-1",
            "workspaceRoots": [str(tmp_path)],
            "taskComplete": {
                "taskMetadata": {
                    "taskId": "task-1",
                    "result": "final answer",
                }
            },
        },
        agent="cline",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    assert add_result == {}
    assert backend.add_calls == [(
        [
            {"role": "user", "content": "current question"},
            {"role": "assistant", "content": "final answer"},
        ],
        {"user_id": "test-user", "conversation_id": "cline:task-1", "async_mode": True},
    )]


def test_cline_cli_normalized_file_hook_events_support_search_and_add(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")
    common = {
        "agentId": "agent-1",
        "conversationId": "conversation-1",
    }

    search_result = run_payload(
        {
            **common,
            "hookName": "prompt_submit",
            "userPromptSubmit": {"prompt": "CLI question", "attachments": []},
        },
        agent="cline",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert "prefers tests" in search_result["contextModification"]

    run_payload(
        {
            **common,
            "hookName": "agent_end",
            "turn": {"outputText": "CLI final answer", "status": "completed"},
            "taskComplete": {"taskMetadata": {}},
        },
        agent="cline",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    assert backend.search_calls[0][0] == "CLI question"
    assert backend.add_calls == [(
        [
            {"role": "user", "content": "CLI question"},
            {"role": "assistant", "content": "CLI final answer"},
        ],
        {
            "user_id": "test-user",
            "conversation_id": "cline:conversation-1",
            "async_mode": True,
        },
    )]


def test_hermes_payload_extra_supports_search_and_add(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")

    search_result = run_payload(
        {
            "hook_event_name": "pre_llm_call",
            "session_id": "s1",
            "cwd": str(tmp_path),
            "extra": {
                "user_message": "remember this",
                "conversation_history": [],
                "is_first_turn": True,
                "model": "gpt-4",
                "platform": "cli",
            },
        },
        agent="hermes",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    assert search_result["context"].startswith("<memos_memory_context")
    assert backend.search_calls[0][0] == "remember this"
    assert store.load("s1") is not None

    add_result = run_payload(
        {
            "hook_event_name": "post_llm_call",
            "session_id": "s1",
            "cwd": str(tmp_path),
            "extra": {
                "user_message": "remember this",
                "assistant_response": "the answer",
                "conversation_history": [],
                "model": "gpt-4",
                "platform": "cli",
            },
        },
        agent="hermes",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    assert add_result == {}
    assert backend.add_calls == [(
        [
            {"role": "user", "content": "remember this"},
            {"role": "assistant", "content": "the answer"},
        ],
        {"user_id": "test-user", "conversation_id": "hermes:s1", "async_mode": True},
    )]
    assert store.load("s1") is None


def test_prompt_empty_and_search_failure_fail_open(tmp_path):
    store = HookStateStore(tmp_path / "state")
    assert run_payload({"hookEventName": "UserPromptSubmit", "sessionId": "s1", "prompt": " "}, store=store) == {}

    def broken(_):
        raise RuntimeError("network failure")

    result = run_payload(
        {"hookEventName": "UserPromptSubmit", "sessionId": "s2", "prompt": "query"},
        config_loader=config,
        backend_factory=broken,
        store=store,
    )
    assert result == {}
    assert store.load("s2") is not None


def test_stop_writes_exact_messages_and_cleans_state(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")
    run_payload(
        {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "turn_id": "t1", "prompt": "raw user"},
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    result = run_payload(
        {"hookEventName": "Stop", "sessionId": "s1", "turnId": "t1", "lastAssistantMessage": "raw answer"},
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert result == {"continue": True, "suppressOutput": True}
    assert backend.add_calls == [(
        [{"role": "user", "content": "raw user"}, {"role": "assistant", "content": "raw answer"}],
        {"user_id": "test-user", "conversation_id": "codex:s1", "async_mode": True},
    )]
    assert store.load("s1", "t1") is None
    run_payload(
        {"hook_event_name": "Stop", "sessionId": "s1", "turnId": "t1", "lastAssistantMessage": "duplicate"},
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert len(backend.add_calls) == 1


def test_hook_agent_id_is_sent_only_when_multi_view_is_enabled(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")
    config_loader = lambda: config(multi_view_enabled=True, agent_id="agent-1")

    run_payload(
        {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "turn_id": "t1", "prompt": "raw user"},
        config_loader=config_loader,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert backend.search_calls[0][1] == {
        "user_id": "test-user",
        "conversation_id": "codex:s1",
        "agent_id": "agent-1",
    }

    run_payload(
        {"hook_event_name": "Stop", "session_id": "s1", "turn_id": "t1", "last_assistant_message": "raw answer"},
        config_loader=config_loader,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert backend.add_calls[0][1] == {
        "user_id": "test-user",
        "conversation_id": "codex:s1",
        "agent_id": "agent-1",
        "async_mode": True,
    }


def test_interleaved_turns_use_turn_specific_state(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")
    common = {"session_id": "same-session"}
    for turn_id, prompt in (("t1", "first prompt"), ("t2", "second prompt")):
        run_payload(
            {"hook_event_name": "UserPromptSubmit", **common, "turn_id": turn_id, "prompt": prompt},
            config_loader=config,
            backend_factory=lambda _: backend,
            store=store,
        )

    run_payload(
        {"hook_event_name": "Stop", **common, "turn_id": "t1", "last_assistant_message": "first answer"},
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert backend.add_calls[0][0] == [
        {"role": "user", "content": "first prompt"},
        {"role": "assistant", "content": "first answer"},
    ]
    assert store.load("same-session", "t2") is not None

    run_payload(
        {"hook_event_name": "Stop", **common, "turn_id": "t2", "last_assistant_message": "second answer"},
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert backend.add_calls[1][0] == [
        {"role": "user", "content": "second prompt"},
        {"role": "assistant", "content": "second answer"},
    ]


def test_turn_id_stop_does_not_consume_session_fallback_state(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")
    run_payload(
        {"hook_event_name": "UserPromptSubmit", "session_id": "same-session", "prompt": "session prompt"},
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    run_payload(
        {"hook_event_name": "Stop", "session_id": "same-session", "turn_id": "unexpected", "last_assistant_message": "wrong"},
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert backend.add_calls == []
    assert store.load("same-session") is not None


def test_stop_uses_transcript_fallback_and_skips_cancelled(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")
    run_payload(
        {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "q"},
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    run_payload(
        {
            "hook_event_name": "Stop",
            "session_id": "s1",
            "messages": [
                {"role": "assistant", "content": "old"},
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "from transcript"},
            ],
        },
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert backend.add_calls[0][0][1]["content"] == "from transcript"

    run_payload(
        {"hook_event_name": "UserPromptSubmit", "session_id": "s2", "prompt": "q2"},
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    run_payload(
        {"hook_event_name": "Stop", "session_id": "s2", "cancelled": True, "lastAssistantMessage": "no"},
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert len(backend.add_calls) == 1
    assert store.load("s2") is None


def test_state_is_private_hashed_atomic_and_ttl_cleaned(tmp_path):
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    store = HookStateStore(tmp_path / "state", now=lambda: now, ttl_seconds=10)
    state = HookTurnState.create(session_key="a/b", conversation_id="codex:a/b", prompt="p", now=now)
    path = store.save(state)
    assert path.name == HookStateStore.key_digest("a/b") + ".json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    old = HookTurnState.create(session_key="old", conversation_id="codex:old", prompt="p", now=now - timedelta(seconds=11))
    old_path = store.save(old)
    unrelated = path.parent / "keep.json"
    unrelated.write_text("keep")
    store.cleanup()
    assert not old_path.exists()
    assert path.exists()
    assert unrelated.exists()


def test_installer_preserves_unrelated_hooks_is_idempotent_and_uninstalls(tmp_path, monkeypatch):
    codex_home = tmp_path / "custom codex"
    codex_home.mkdir()
    config_path = codex_home / "hooks.json"
    unrelated = {"type": "command", "command": "/custom/hook", "timeout": 5}
    matched_entry = {"matcher": "only-special-prompts", "hooks": [unrelated]}
    config_path.write_text(json.dumps({"other": {"x": 1}, "hooks": {"UserPromptSubmit": [matched_entry]}}))
    executable = tmp_path / "bin with spaces" / "memos"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        install_hook("codex")
        install_hook("codex")
    installed = json.loads(config_path.read_text())
    assert installed["other"] == {"x": 1}
    for event in ("UserPromptSubmit", "Stop"):
        entries = installed["hooks"][event]
        managed_entries = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and isinstance(entry.get("hooks"), list)
            and any(is_managed_hook(item) for item in entry["hooks"])
        ]
        assert len(managed_entries) == 1
        assert set(managed_entries[0]) == {"hooks"}
        assert len(managed_entries[0]["hooks"]) == 1
        assert "bin with spaces" in managed_entries[0]["hooks"][0]["command"]
    assert installed["hooks"]["UserPromptSubmit"][0] == matched_entry
    assert len(installed["hooks"]["UserPromptSubmit"]) == 2
    assert not is_managed_hook({"command": "/custom/memos hook run --agent codex-extra"})
    uninstall_hook("codex")
    uninstalled = json.loads(config_path.read_text())
    assert uninstalled == {"other": {"x": 1}, "hooks": {"UserPromptSubmit": [matched_entry]}}


def test_installer_rejects_malformed_json(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "hooks.json").write_text("not json")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=tmp_path / "memos"):
        with pytest.raises(HookConfigError):
            install_hook("codex")


def test_installer_treats_empty_hooks_json_as_new_config(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    config_path = codex_home / "hooks.json"
    config_path.write_text("\n")
    executable = tmp_path / "memos"
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        install_hook("codex")
    assert set(json.loads(config_path.read_text())["hooks"]) == {"UserPromptSubmit", "Stop"}


@pytest.mark.parametrize(
    ("agent", "expected_suffix"),
    [
        ("trae", Path(".trae/hooks.json")),
        ("trae-cn", Path(".trae-cn/hooks.json")),
        ("antigravity", Path(".gemini/config/hooks.json")),
        ("hermes", Path(".hermes/plugins/memos-memory")),
        ("cline", Path(".cline/plugins/memos-memory")),
        ("copilot", Path(".copilot/hooks/memos-memory.json")),
        ("opencode", Path(".config/opencode/plugins/memos-memory.js")),
        ("openclaw", Path(".openclaw/extensions/memos-memory")),
    ],
)
def test_new_native_hook_agents_are_registered(agent, expected_suffix):
    assert is_native_hook_agent(agent)
    spec = get_hook_agent_spec(agent)
    assert spec.config_path().as_posix().endswith(expected_suffix.as_posix())
    if agent == "cursor":
        assert spec.search_injection_enabled is False
        assert spec.search_hook_enabled is True


@pytest.mark.parametrize(
    ("agent", "expected_path", "events", "wrapped", "layout"),
    [
        ("trae", ".trae/hooks.json", ("UserPromptSubmit", "Stop"), True, "nested"),
        ("trae-cn", ".trae-cn/hooks.json", ("UserPromptSubmit", "Stop"), True, "nested"),
        ("antigravity", ".gemini/config/hooks.json", ("PreInvocation", "Stop"), False, "antigravity"),
    ],
)
def test_installer_writes_added_native_hook_configs(
    tmp_path,
    monkeypatch,
    agent,
    expected_path,
    events,
    wrapped,
    layout,
):
    executable = tmp_path / "bin with spaces" / "memos"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    target_path = Path.home() / expected_path

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        installed_path = install_hook(agent)

    assert installed_path == target_path
    data = json.loads(target_path.read_text())
    if agent == "copilot":
        assert data["version"] == 1

    if layout == "antigravity":
        event_root = data["memos-memory"]
        for event in events:
            hook = event_root[event][0]
            assert is_managed_hook(hook, agent)
            assert "memos-antigravity-hook-adapter.py" in hook["command"]
            assert "statusMessage" not in hook
        adapter = target_path.parent / "memos-antigravity-hook-adapter.py"
        assert adapter.is_file()
        assert "bin with spaces" in adapter.read_text()
        assert f'"--agent", "{agent}"' in adapter.read_text()
    else:
        for event in events:
            entries = data["hooks"][event]
            hook = entries[0]["hooks"][0] if wrapped else entries[0]
            assert is_managed_hook(hook, agent)
            assert "bin with spaces" in hook["command"]
            assert f"--agent {agent}" in hook["command"]
            assert "--event" in hook["command"]

    uninstall_hook(agent)
    data = json.loads(target_path.read_text())
    if layout == "antigravity":
        assert "memos-memory" not in data
        assert not (target_path.parent / "memos-antigravity-hook-adapter.py").exists()
    else:
        assert "hooks" not in data


def test_trae_installer_writes_version_field(tmp_path, monkeypatch):
    home = tmp_path / "home"
    trae_home = home / ".trae"
    executable = tmp_path / "bin with spaces" / "memos"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("HOME", str(home))

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        installed_path = install_hook("trae")

    assert installed_path == trae_home / "hooks.json"
    data = json.loads(installed_path.read_text())
    assert data["version"] == 1
    assert "hooks" in data

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        install_hook("trae")
    data = json.loads(installed_path.read_text())
    assert data["version"] == 1

    uninstall_hook("trae")
    data = json.loads(installed_path.read_text())
    assert "hooks" not in data
    assert data.get("version") == 1


def test_copilot_installer_writes_dedicated_hook_file(tmp_path, monkeypatch):
    copilot_home = tmp_path / ".copilot"
    executable = tmp_path / "bin with spaces" / "memos"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        installed_path = install_hook("copilot")

    assert installed_path == copilot_home / "hooks" / "memos-memory.json"
    data = json.loads(installed_path.read_text())
    assert data["version"] == 1
    for event in ("userPromptTransformed", "agentStop"):
        hook = data["hooks"][event][0]
        assert is_managed_hook(hook, "copilot")
        assert "bin with spaces" in hook["command"]
        assert hook["bash"] == hook["command"]
        assert hook["timeoutSec"] == 60
        assert "statusMessage" not in hook
        assert "--agent copilot" in hook["command"]
        assert "--event" in hook["command"]

    uninstall_hook("copilot")
    assert not installed_path.exists()


def test_copilot_installer_writes_repo_cloud_hook_too(tmp_path, monkeypatch):
    copilot_home = tmp_path / ".copilot"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".github" / "hooks").mkdir(parents=True)
    executable = tmp_path / "bin with spaces" / "memos"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MEMOS_COPILOT_REPO_ROOT", str(repo))
    monkeypatch.chdir(repo)

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        installed_path = install_hook("copilot")

    assert installed_path == copilot_home / "hooks" / "memos-memory.json"
    user_config = json.loads(installed_path.read_text())
    cloud_path = repo / ".github" / "hooks" / "memos-memory.json"
    cloud_config = json.loads(cloud_path.read_text())

    assert user_config["version"] == 1
    assert cloud_config["version"] == 1
    assert cloud_config["hooks"]["userPromptTransformed"][0]["command"] == "memos hook run --agent copilot --event userPromptTransformed"
    assert cloud_config["hooks"]["agentStop"][0]["command"] == "memos hook run --agent copilot --event agentStop"
    for event in ("userPromptTransformed", "agentStop"):
        hook = cloud_config["hooks"][event][0]
        assert hook["bash"] == hook["command"]
        assert hook["timeoutSec"] == 60
        assert "statusMessage" not in hook

    uninstall_hook("copilot")
    assert not installed_path.exists()
    assert not cloud_path.exists()


def test_copilot_agent_stop_reads_events_jsonl_transcript_fallback(tmp_path, monkeypatch):
    """Copilot agentStop may omit transcriptPath; use its session-state events."""
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "hook-state")
    copilot_home = tmp_path / ".copilot"
    events_path = copilot_home / "session-state" / "session-1" / "events.jsonl"
    events_path.parent.mkdir(parents=True)
    events_path.write_text(
        "\n".join(
            [
                json.dumps({"type": "user.message", "data": {"content": "user question"}}),
                json.dumps({"type": "assistant.turn_start", "data": {"turnId": "1"}}),
                json.dumps(
                    {
                        "type": "assistant.message",
                        "data": {"content": "final assistant answer", "toolRequests": []},
                    }
                ),
                json.dumps({"type": "assistant.turn_end", "data": {"turnId": "1"}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("COPILOT_HOME", str(copilot_home))

    run_payload(
        {
            "hook_event_name": "userPromptTransformed",
            "sessionId": "session-1",
            "prompt": "user question",
            "transformedPrompt": "user question",
        },
        agent="copilot",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    run_payload(
        {
            "hook_event_name": "agentStop",
            "sessionId": "session-1",
            "stopReason": "end_turn",
            "transcriptPath": "",
        },
        agent="copilot",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    assert backend.add_calls == [
        (
            [
                {"role": "user", "content": "user question"},
                {"role": "assistant", "content": "final assistant answer"},
            ],
            {
                "user_id": "test-user",
                "conversation_id": "copilot:session-1",
                "async_mode": True,
            },
        )
    ]


def test_cursor_installer_writes_prompt_capture_and_add_hooks(tmp_path, monkeypatch):
    cursor_home = tmp_path / ".cursor"
    cursor_home.mkdir()
    executable = tmp_path / "memos"
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("CURSOR_HOME", str(cursor_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        install_hook("cursor")

    config = json.loads((cursor_home / "hooks.json").read_text())
    assert "beforeSubmitPrompt" in config.get("hooks", {})
    assert "afterAgentResponse" in config.get("hooks", {})
    before_hook = config["hooks"]["beforeSubmitPrompt"][0]
    assert is_managed_hook(before_hook, "cursor")
    hook = config["hooks"]["afterAgentResponse"][0]
    assert is_managed_hook(hook, "cursor")


def test_cursor_installer_removes_retired_managed_stop_hook(tmp_path, monkeypatch):
    cursor_home = tmp_path / ".cursor"
    cursor_home.mkdir()
    executable = tmp_path / "memos"
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("CURSOR_HOME", str(cursor_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (cursor_home / "hooks.json").write_text(
        json.dumps(
            {
                "version": 1,
                "hooks": {
                    "stop": [
                        {
                            "command": f"{executable} hook run --agent cursor --event stop",
                            "timeout": 60,
                        }
                    ],
                    "customEvent": [{"command": "/usr/bin/custom-hook"}],
                },
            }
        )
    )

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        install_hook("cursor")

    config = json.loads((cursor_home / "hooks.json").read_text())
    assert "stop" not in config["hooks"]
    assert config["hooks"]["customEvent"] == [{"command": "/usr/bin/custom-hook"}]
    assert len(config["hooks"]["afterAgentResponse"]) == 1
    assert is_managed_hook(config["hooks"]["afterAgentResponse"][0], "cursor")


@pytest.mark.parametrize(
    ("agent", "env", "expected_path", "events", "wrapped", "yaml_file"),
    [
        ("codex", "CODEX_HOME", ".codex/hooks.json", ("UserPromptSubmit", "Stop"), True, False),
        ("cursor", "CURSOR_HOME", ".cursor/hooks.json", ("beforeSubmitPrompt", "afterAgentResponse"), False, False),
        ("claude", "CLAUDE_CONFIG_DIR", ".claude/settings.json", ("UserPromptSubmit", "Stop"), True, False),
    ],
)
def test_installer_writes_native_hook_config_for_config_based_agents(
    tmp_path,
    monkeypatch,
    agent,
    env,
    expected_path,
    events,
    wrapped,
    yaml_file,
):
    executable = tmp_path / "bin with spaces" / "memos"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    target_path = tmp_path / expected_path
    monkeypatch.setenv(env, str(target_path.parent))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        installed_path = install_hook(agent)

    assert installed_path == target_path
    data = yaml.safe_load(target_path.read_text()) if yaml_file else json.loads(target_path.read_text())
    for event in events:
        entries = data["hooks"][event]
        hook = entries[0]["hooks"][0] if wrapped else entries[0]
        assert is_managed_hook(hook, agent)
        assert "bin with spaces" in hook["command"]
        assert f"--agent {agent}" in hook["command"]
        assert "--event" in hook["command"]

    uninstall_hook(agent)
    data = yaml.safe_load(target_path.read_text()) if yaml_file else json.loads(target_path.read_text())
    assert "hooks" not in data


def test_hermes_installer_writes_enabled_plugin_and_migrates_shell_hooks(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    executable = tmp_path / "bin with spaces" / "memos"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    command_prefix = shlex.quote(str(executable))
    config_path = hermes_home / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "hooks_auto_accept": True,
                "hooks": {
                    "pre_llm_call": [
                        {
                            "type": "command",
                            "command": f"{command_prefix} hook run --agent hermes --event pre_llm_call",
                        },
                        {"type": "command", "command": "/usr/bin/custom-hook"},
                    ],
                    "post_llm_call": [
                        {
                            "type": "command",
                            "command": f"{command_prefix} hook run --agent hermes --event post_llm_call",
                        }
                    ],
                },
                "plugins": {
                    "enabled": ["other-plugin", "memos-memory"],
                    "disabled": ["memos-memory", "blocked-plugin"],
                    "settings": {"keep": True},
                },
                "other": {"keep": True},
            },
            sort_keys=False,
        )
    )

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        installed_path = install_hook("hermes")
        assert install_hook("hermes") == installed_path

    plugin_dir = hermes_home / "plugins" / "memos-memory"
    assert installed_path == plugin_dir
    manifest = yaml.safe_load((plugin_dir / "plugin.yaml").read_text())
    assert manifest["name"] == "memos-memory"
    assert manifest["kind"] == "standalone"
    assert manifest["hooks"] == ["pre_llm_call", "post_llm_call"]

    entry = plugin_dir / "__init__.py"
    content = entry.read_text()
    assert "memos hook run --agent hermes" in content
    assert str(executable) in content
    assert 'ctx.register_hook("pre_llm_call", _pre_llm_call)' in content
    assert 'ctx.register_hook("post_llm_call", _post_llm_call)' in content

    installed_config = yaml.safe_load(config_path.read_text())
    assert installed_config["hooks_auto_accept"] is True
    assert installed_config["hooks"]["pre_llm_call"] == [
        {"type": "command", "command": "/usr/bin/custom-hook"}
    ]
    assert "post_llm_call" not in installed_config["hooks"]
    assert installed_config["plugins"]["enabled"] == ["other-plugin", "memos-memory"]
    assert installed_config["plugins"]["disabled"] == ["blocked-plugin"]
    assert installed_config["plugins"]["settings"] == {"keep": True}
    assert installed_config["other"] == {"keep": True}

    namespace = runpy.run_path(str(entry))
    callbacks = {}

    class FakePluginContext:
        def register_hook(self, event, callback):
            callbacks[event] = callback

    namespace["register"](FakePluginContext())
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs, json.loads(kwargs["input"])))
        stdout = json.dumps({"context": "retrieved context"}) if argv[-1] == "pre_llm_call" else "{}"
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    with patch.object(namespace["subprocess"], "run", side_effect=fake_run):
        result = callbacks["pre_llm_call"](
            session_id="s1",
            user_message="remember this",
            turn_id="t1",
            model="gpt-4",
            platform="desktop",
        )
        callbacks["post_llm_call"](
            session_id="s1",
            user_message="remember this",
            assistant_response="the answer",
            turn_id="t1",
            model="gpt-4",
            platform="desktop",
        )

    assert result == {"context": "retrieved context"}
    assert [call[0][-1] for call in calls] == ["pre_llm_call", "post_llm_call"]
    assert calls[0][0][0] == str(executable)
    assert calls[0][1]["shell"] is False
    assert calls[0][2]["session_id"] == "s1"
    assert calls[0][2]["turn_id"] == "t1"
    assert calls[0][2]["extra"]["user_message"] == "remember this"
    assert calls[1][2]["extra"]["assistant_response"] == "the answer"

    assert uninstall_hook("hermes") == plugin_dir
    assert not plugin_dir.exists()
    uninstalled_config = yaml.safe_load(config_path.read_text())
    assert uninstalled_config["plugins"]["enabled"] == ["other-plugin"]
    assert uninstalled_config["plugins"]["disabled"] == ["blocked-plugin"]
    assert uninstalled_config["hooks"]["pre_llm_call"] == [
        {"type": "command", "command": "/usr/bin/custom-hook"}
    ]


def test_hermes_installer_does_not_overwrite_user_owned_plugin(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    plugin_dir = hermes_home / "plugins" / "memos-memory"
    plugin_dir.mkdir(parents=True)
    entry = plugin_dir / "__init__.py"
    entry.write_text("def register(ctx):\n    pass\n")
    config_path = hermes_home / "config.yaml"
    config_path.write_text(yaml.safe_dump({"plugins": {"enabled": ["memos-memory"]}}))
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=tmp_path / "memos"):
        with pytest.raises(HookConfigError, match="user-owned Hermes plugin"):
            install_hook("hermes")

    assert uninstall_hook("hermes") is None
    assert entry.exists()
    assert yaml.safe_load(config_path.read_text())["plugins"]["enabled"] == ["memos-memory"]


def test_cline_installer_writes_managed_plugin(tmp_path, monkeypatch):
    cline_home = tmp_path / ".cline"
    executable = tmp_path / "bin with spaces" / "memos"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    legacy_entry = cline_home / "plugins" / "memos-memory.js"
    legacy_entry.parent.mkdir(parents=True)
    legacy_entry.write_text("// Managed by MemOS CLI: memos hook run --agent cline\n")
    stale_install = cline_home / "plugins" / "_installed" / "local" / "memos-memory.js-old"
    stale_install.mkdir(parents=True)
    (stale_install / "memos-memory.js").write_text(
        "// Managed by MemOS CLI: memos hook run --agent cline\n"
    )
    user_install = cline_home / "plugins" / "_installed" / "local" / "user-plugin"
    user_install.mkdir(parents=True)
    user_entry = user_install / "index.js"
    user_entry.write_text("export default { name: 'user-plugin' }\n")
    monkeypatch.setenv("CLINE_HOME", str(cline_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        installed_path = install_hook("cline")

    assert installed_path == cline_home / "plugins" / "memos-memory"
    assert installed_path.is_dir()
    assert not legacy_entry.exists()
    assert not stale_install.exists()
    assert user_entry.exists()
    package = json.loads((installed_path / "package.json").read_text())
    assert package == {
        "name": "memos-memory",
        "version": "1.0.0",
        "private": True,
        "type": "module",
        "cline": {
            "plugins": [
                {
                    "paths": ["./index.js"],
                    "capabilities": ["hooks", "messageBuilders"],
                }
            ]
        },
    }
    content = (installed_path / "index.js").read_text()
    assert "memos hook run --agent cline" in content
    assert "UserPromptSubmit" in content
    assert "TaskComplete" in content
    assert "bin with spaces" in content
    assert 'name: "memos-memory-context"' in content
    assert "afterRun" in content
    assert 'void runMemos("TaskComplete"' in content
    assert 'await runMemos("TaskComplete"' not in content
    assert "registerMessageBuilder" in content
    assert "beforeModel" not in content
    assert "result.outputText" in content
    assert "export default plugin" in content

    ide_hooks_dir = Path.home() / "Documents" / "Cline" / "Hooks"
    prompt_hook = ide_hooks_dir / "UserPromptSubmit"
    complete_hook = ide_hooks_dir / "TaskComplete"
    assert prompt_hook.is_file()
    assert complete_hook.is_file()
    assert os.access(prompt_hook, os.X_OK)
    assert os.access(complete_hook, os.X_OK)
    assert "--event UserPromptSubmit" in prompt_hook.read_text()
    assert "--event TaskComplete" in complete_hook.read_text()
    assert "bin with spaces" in prompt_hook.read_text()

    uninstall_hook("cline")
    assert not installed_path.exists()
    assert not prompt_hook.exists()
    assert not complete_hook.exists()


def test_cline_uninstall_keeps_user_owned_plugin(tmp_path, monkeypatch):
    cline_home = tmp_path / ".cline"
    plugin_path = cline_home / "plugins" / "memos-memory"
    plugin_path.mkdir(parents=True)
    entry = plugin_path / "index.js"
    entry.write_text("export default { name: \"user-owned\" }\n")
    monkeypatch.setenv("CLINE_HOME", str(cline_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert uninstall_hook("cline") is None
    assert plugin_path.exists()
    assert entry.exists()


def test_cline_installer_does_not_overwrite_user_owned_ide_hook(tmp_path, monkeypatch):
    home = tmp_path / "home"
    hooks_dir = home / "Documents" / "Cline" / "Hooks"
    hooks_dir.mkdir(parents=True)
    prompt_hook = hooks_dir / "UserPromptSubmit"
    prompt_hook.write_text("#!/bin/sh\necho user-owned\n")
    executable = tmp_path / "memos"
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLINE_DIR", str(tmp_path / ".cline"))

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        with pytest.raises(HookConfigError, match="user-owned Cline hook"):
            install_hook("cline")

    assert prompt_hook.read_text() == "#!/bin/sh\necho user-owned\n"
    assert not (tmp_path / ".cline" / "plugins" / "memos-memory").exists()


def test_cline_ide_hook_scripts_pipe_payloads_to_memos(tmp_path, monkeypatch):
    home = tmp_path / "home"
    executable = tmp_path / "bin with spaces" / "memos"
    executable.parent.mkdir()
    log_path = tmp_path / "calls.jsonl"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "payload = json.loads(sys.stdin.read())\n"
        "with open(os.environ['MEMOS_TEST_LOG'], 'a', encoding='utf-8') as handle:\n"
        "    handle.write(json.dumps({'event': sys.argv[-1], 'payload': payload}) + '\\n')\n"
        "print(json.dumps({'cancel': False, 'contextModification': 'memory context'}))\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLINE_DIR", str(tmp_path / ".cline"))

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        install_hook("cline")

    hooks_dir = home / "Documents" / "Cline" / "Hooks"
    search_payload = {
        "hookName": "UserPromptSubmit",
        "taskId": "task-1",
        "userPromptSubmit": {"prompt": "current question", "attachments": []},
    }
    add_payload = {
        "hookName": "TaskComplete",
        "taskId": "task-1",
        "taskComplete": {"taskMetadata": {"result": "final answer"}},
    }
    env = {**os.environ, "MEMOS_TEST_LOG": str(log_path)}
    search = subprocess.run(
        [str(hooks_dir / "UserPromptSubmit")],
        input=json.dumps(search_payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    add = subprocess.run(
        [str(hooks_dir / "TaskComplete")],
        input=json.dumps(add_payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert search.returncode == 0, search.stderr
    assert add.returncode == 0, add.stderr
    assert json.loads(search.stdout)["contextModification"] == "memory context"
    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert calls == [
        {"event": "UserPromptSubmit", "payload": search_payload},
        {"event": "TaskComplete", "payload": add_payload},
    ]


def test_cline_plugin_uses_runtime_hook_payloads_for_search_and_add(tmp_path):
    from memos_cli.hooks.host_templates import cline_plugin, cline_plugin_package_json

    executable = tmp_path / "fake-memos.py"
    log_path = tmp_path / "calls.jsonl"
    executable.write_text(
        "import json, os, sys\n"
        "payload = json.loads(sys.stdin.read())\n"
        "with open(os.environ['MEMOS_TEST_LOG'], 'a', encoding='utf-8') as handle:\n"
        "    handle.write(json.dumps({'event': sys.argv[-1], 'payload': payload}) + '\\n')\n"
        "print(json.dumps({'contextModification': 'retrieved memory'} if sys.argv[-1] == 'UserPromptSubmit' else {}))\n",
        encoding="utf-8",
    )
    plugin_dir = tmp_path / "memos-memory"
    plugin_dir.mkdir()
    (plugin_dir / "package.json").write_text(cline_plugin_package_json(), encoding="utf-8")
    plugin_path = plugin_dir / "index.js"
    plugin_path.write_text(
        cline_plugin([sys.executable, str(executable)], get_hook_agent_spec("cline")),
        encoding="utf-8",
    )
    driver_path = tmp_path / "driver.mjs"
    driver_path.write_text(
        f'''const plugin = (await import({json.dumps(plugin_path.as_uri())})).default
let messageBuilder
plugin.setup({{
  registerMessageBuilder(builder) {{ messageBuilder = builder }},
}}, {{
  session: {{ sessionId: "session-from-setup" }},
  workspaceInfo: {{ rootPath: "/workspace" }},
}})
const messages = [
  {{ role: "user", content: [{{ type: "text", text: "older question" }}] }},
  {{ role: "assistant", content: [{{ type: "text", text: "older answer" }}] }},
  {{ role: "user", content: [{{ type: "text", text: "current question" }}] }},
  {{
    role: "user",
    content: [{{ type: "text", text: "completion reminder" }}],
    metadata: {{ userRunSpan: 0, displayRole: "system" }},
  }},
]
const snapshot = {{
  agentId: "agent-1",
  conversationId: "conversation-1",
  runId: "run-1",
  iteration: 1,
  messages,
}}
const searchMessages = await messageBuilder.build(messages)
const repeatedMessages = await messageBuilder.build(messages)
await plugin.hooks.afterRun({{
  snapshot: {{ ...snapshot, messages: [...messages, {{ role: "assistant", content: [{{ type: "text", text: "final answer" }}] }}] }},
  result: {{
    status: "completed",
    outputText: "final answer line 1\\nfinal answer line 2",
    messages: [...messages, {{ role: "assistant", content: [{{ type: "text", text: "final answer" }}] }}],
  }},
}})
console.log(JSON.stringify({{ builderName: messageBuilder.name, searchMessages, repeatedMessages }}))
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["node", str(driver_path)],
        capture_output=True,
        text=True,
        env={**os.environ, "MEMOS_TEST_LOG": str(log_path)},
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["builderName"] == "memos-memory-context"
    assert result["searchMessages"][2]["content"] == [
        {"type": "text", "text": "retrieved memory"},
        {"type": "text", "text": "current question"},
    ]
    assert result["searchMessages"][-1]["content"] == [
        {"type": "text", "text": "completion reminder"}
    ]
    assert result["repeatedMessages"] == result["searchMessages"]
    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert [call["event"] for call in calls] == ["UserPromptSubmit", "TaskComplete"]
    assert calls[0]["payload"] == {
        "session_id": "session-from-setup",
        "prompt": "current question",
    }
    assert calls[1]["payload"] == {
        "session_id": "session-from-setup",
        "prompt": "current question",
        "last_assistant_message": "final answer line 1\nfinal answer line 2",
        "status": "completed",
    }


def test_opencode_installer_writes_managed_plugin(tmp_path, monkeypatch):
    config_dir = tmp_path / "opencode-config"
    executable = tmp_path / "bin with spaces" / "memos"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        installed_path = install_hook("opencode")

    assert installed_path == config_dir / "plugins" / "memos-memory.js"
    content = installed_path.read_text()
    assert "memos hook run --agent opencode" in content
    assert "chat.message" in content
    assert "session.idle" in content
    assert "bin with spaces" in content
    assert "export const MemosMemoryPlugin" in content

    uninstall_hook("opencode")
    assert not installed_path.exists()


def test_opencode_uninstall_keeps_user_owned_plugin(tmp_path, monkeypatch):
    config_dir = tmp_path / "opencode-config"
    plugin_path = config_dir / "plugins" / "memos-memory.js"
    plugin_path.parent.mkdir(parents=True)
    plugin_path.write_text("export const UserPlugin = async () => ({})\n")
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert uninstall_hook("opencode") is None
    assert plugin_path.exists()


def test_openclaw_installer_writes_plugin_dir_and_enables_entry(tmp_path, monkeypatch):
    state_dir = tmp_path / ".openclaw"
    executable = tmp_path / "bin with spaces" / "memos"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("OPENCLAW_STATE_DIR", str(state_dir))
    monkeypatch.delenv("OPENCLAW_CONFIG_PATH", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    config_path = state_dir / "openclaw.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"agents": {"defaults": {"model": "test"}}}))

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        installed_path = install_hook("openclaw")

    plugin_dir = state_dir / "extensions" / "memos-memory"
    assert installed_path == plugin_dir
    manifest = json.loads((plugin_dir / "openclaw.plugin.json").read_text())
    assert manifest["id"] == "memos-memory"
    assert manifest["configSchema"] == {"type": "object", "additionalProperties": False, "properties": {}}
    assert "entry" not in manifest
    package = json.loads((plugin_dir / "package.json").read_text())
    assert package["type"] == "module"
    assert package["openclaw"]["extensions"] == ["./index.js"]
    entry = (plugin_dir / "index.js").read_text()
    assert "memos hook run --agent openclaw" in entry
    assert 'api.on("before_prompt_build"' in entry
    assert 'api.on("agent_end"' in entry
    assert "prependContext" in entry
    config = json.loads(config_path.read_text())
    assert config["agents"] == {"defaults": {"model": "test"}}
    assert config["plugins"]["entries"]["memos-memory"] == {
        "enabled": True,
        "hooks": {"allowConversationAccess": True, "allowPromptInjection": True},
    }
    assert "load" not in config["plugins"]

    uninstall_hook("openclaw")
    assert not plugin_dir.exists()
    config = json.loads(config_path.read_text())
    assert "memos-memory" not in config["plugins"]["entries"]


def test_openclaw_plugin_uses_agent_end_messages_for_add(tmp_path):
    from memos_cli.hooks.host_templates import openclaw_plugin_entry

    executable = tmp_path / "fake-memos.py"
    log_path = tmp_path / "calls.jsonl"
    executable.write_text(
        "import json, os, sys\n"
        "payload = json.loads(sys.stdin.read())\n"
        "with open(os.environ['MEMOS_TEST_LOG'], 'a', encoding='utf-8') as handle:\n"
        "    handle.write(json.dumps({'event': sys.argv[-1], 'payload': payload}) + '\\n')\n"
        "print(json.dumps({'prependContext': 'retrieved memory'} if sys.argv[-1] == 'before_prompt_build' else {}))\n",
        encoding="utf-8",
    )
    plugin_path = tmp_path / "memos-memory.mjs"
    plugin_path.write_text(
        openclaw_plugin_entry([sys.executable, str(executable)], get_hook_agent_spec("openclaw")),
        encoding="utf-8",
    )
    driver_path = tmp_path / "driver.mjs"
    driver_path.write_text(
        f'''const plugin = (await import({json.dumps(plugin_path.as_uri())})).default
const listeners = {{}}
plugin.register({{ on(event, callback) {{ listeners[event] = callback }} }})
const ctx = {{ sessionKey: "session-1", sessionId: "uuid-1", runId: "run-1" }}
const searchResult = await listeners["before_prompt_build"]({{
  prompt: "user question",
  messages: [{{ role: "user", content: "user question" }}],
}}, ctx)
await listeners["agent_end"]({{
  runId: "run-1",
  messages: [
    {{ role: "user", content: "user question" }},
    {{ role: "assistant", content: [{{ type: "text", text: "tool preamble" }}] }},
    {{ role: "toolResult", content: [{{ type: "text", text: "tool output" }}] }},
    {{
      role: "assistant",
      content: [
        {{ type: "thinking", text: "hidden reasoning" }},
        {{ type: "text", text: "final answer line 1" }},
        {{ type: "text", text: "final answer line 2" }},
      ],
    }},
  ],
  success: true,
  durationMs: 25,
}}, ctx)
console.log(JSON.stringify({{ searchResult }}))
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["node", str(driver_path)],
        capture_output=True,
        text=True,
        env={**os.environ, "MEMOS_TEST_LOG": str(log_path)},
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"searchResult": {"prependContext": "retrieved memory"}}
    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert [call["event"] for call in calls] == ["before_prompt_build", "agent_end"]
    assert calls[1]["payload"] == {
        "session_id": "session-1",
        "prompt": "user question",
        "last_assistant_message": "final answer line 1\nfinal answer line 2",
    }


def test_deepseek_installer_writes_cordis_plugin_and_patch(tmp_path, monkeypatch):
    dsh_home = tmp_path / ".dsh"
    executable = tmp_path / "bin with spaces" / "memos"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n")
    monkeypatch.setenv("DSH_HOME", str(dsh_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    patch_path = dsh_home / "cordis.patch.yml"
    patch_path.parent.mkdir(parents=True)
    existing_row = {"insert": [{"id": "other-plugin", "name": "/opt/other.js"}]}
    patch_path.write_text(yaml.safe_dump([existing_row]))

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        installed_path = install_hook("deepseek")

    plugin_path = dsh_home / "plugins" / "memos-memory.js"
    assert installed_path == plugin_path
    content = plugin_path.read_text()
    assert "memos hook run --agent deepseek" in content
    assert 'ctx.on("agent/pre-step"' in content
    assert 'ctx.on("agent/turn-stopping"' in content
    assert 'export const name = "memos-memory"' in content
    assert "export function apply(ctx)" in content

    patch_data = yaml.safe_load(patch_path.read_text())
    assert existing_row in patch_data
    managed_rows = [
        row
        for operation in patch_data
        for row in operation.get("insert", [])
        if row.get("id") == "memos-memory"
    ]
    assert managed_rows == [{"id": "memos-memory", "name": str(plugin_path)}]

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        install_hook("deepseek")
    patch_data = yaml.safe_load(patch_path.read_text())
    managed_rows = [
        row
        for operation in patch_data
        for row in operation.get("insert", [])
        if row.get("id") == "memos-memory"
    ]
    assert len(managed_rows) == 1

    uninstall_hook("deepseek")
    assert not plugin_path.exists()
    patch_data = yaml.safe_load(patch_path.read_text())
    assert patch_data == [existing_row]


def test_deepseek_plugin_uses_agent_session_for_turn_stopping_add(tmp_path):
    from memos_cli.hooks.host_templates import deepseek_plugin

    executable = tmp_path / "fake-memos.py"
    log_path = tmp_path / "calls.jsonl"
    executable.write_text(
        "import json, os, sys\n"
        "payload = json.loads(sys.stdin.read())\n"
        "with open(os.environ['MEMOS_TEST_LOG'], 'a', encoding='utf-8') as handle:\n"
        "    handle.write(json.dumps({'event': sys.argv[-1], 'payload': payload}) + '\\n')\n"
        "print(json.dumps({'context': 'retrieved memory'} if sys.argv[-1] == 'agent/pre-step' else {}))\n",
        encoding="utf-8",
    )
    plugin_path = tmp_path / "memos-memory.mjs"
    plugin_path.write_text(
        deepseek_plugin([sys.executable, str(executable)], get_hook_agent_spec("deepseek")),
        encoding="utf-8",
    )
    driver_path = tmp_path / "driver.mjs"
    driver_path.write_text(
        f'''const plugin = await import({json.dumps(plugin_path.as_uri())})
const listeners = {{}}
plugin.apply({{ on(event, callback) {{ listeners[event] = callback }} }})
const agent = {{
  session: {{
    id: "session-1",
    events: [{{
      type: "assistant/message",
      data: {{ turn: 7, step: 1, message: {{ content: [{{ type: "text", text: "final answer" }}] }} }},
    }}],
  }},
}}
const promptMessage = {{
  id: "prompt-1",
  role: "user",
  content: [{{ type: "text", text: "user question" }}],
  source: {{ kind: "user" }},
}}
const decision = await listeners["agent/pre-step"](
  {{ agent, messages: [promptMessage], turn: 7, step: 1, signal: {{}} }},
  async () => ({{ kind: "enter", messages: [promptMessage] }}),
)
await listeners["agent/turn-stopping"]({{ agent, turn: 7, signal: {{}} }})
console.log(JSON.stringify({{ decision }}))
''',
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["node", str(driver_path)],
        capture_output=True,
        text=True,
        env={**os.environ, "MEMOS_TEST_LOG": str(log_path)},
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["decision"]["kind"] == "enter"
    assert result["decision"]["messages"][-1]["content"] == [
        {"type": "text", "text": "retrieved memory"}
    ]
    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert [call["event"] for call in calls] == ["agent/pre-step", "agent/turn-stopping"]
    assert calls[1]["payload"] == {
        "session_id": "session-1",
        "turn_id": "7",
        "prompt": "user question",
        "last_assistant_message": "final answer",
    }


def test_antigravity_stop_waits_for_fully_idle(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")
    run_payload(
        {"hook_event_name": "PreInvocation", "session_id": "s1", "prompt": "raw user"},
        agent="antigravity",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    result = run_payload(
        {"hook_event_name": "Stop", "session_id": "s1", "fullyIdle": False, "lastAssistantMessage": "partial"},
        agent="antigravity",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert result == {}
    assert backend.add_calls == []
    assert store.load("s1") is not None

    run_payload(
        {"hook_event_name": "Stop", "session_id": "s1", "fullyIdle": True, "lastAssistantMessage": "final answer"},
        agent="antigravity",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert backend.add_calls == [(
        [{"role": "user", "content": "raw user"}, {"role": "assistant", "content": "final answer"}],
        {"user_id": "test-user", "conversation_id": "antigravity:s1", "async_mode": True},
    )]
    assert store.load("s1") is None


def test_antigravity_local_adapter_normalizes_old_cli_payload(tmp_path, monkeypatch):
    """The generated adapter makes beta.17 understand Antigravity payloads."""
    from memos_cli.hooks.installer import install_hook

    home = tmp_path / "home"
    executable = tmp_path / "bin with spaces" / "memos"
    log_path = tmp_path / "adapter-calls.jsonl"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "payload = json.loads(sys.stdin.read())\n"
        "with open(os.environ['MEMOS_TEST_LOG'], 'a', encoding='utf-8') as handle:\n"
        "    handle.write(json.dumps({'event': sys.argv[-1], 'payload': payload}) + '\\n')\n"
        "print(json.dumps({'injectSteps': []} if sys.argv[-1] == 'PreInvocation' else {}))\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MEMOS_TEST_LOG", str(log_path))

    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=executable):
        hooks_path = install_hook("antigravity")

    config = json.loads(hooks_path.read_text())
    search_command = shlex.split(config["memos-memory"]["PreInvocation"][0]["command"])
    add_command = shlex.split(config["memos-memory"]["Stop"][0]["command"])
    search = subprocess.run(
        search_command,
        input=json.dumps(
            {
                "hookName": "PreInvocation",
                "sessionId": "ag-adapter-1",
                "lastUserInput": "<USER_REQUEST>原始用户问题</USER_REQUEST><ADDITIONAL_METADATA>ignored",
            }
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    add = subprocess.run(
        add_command,
        input=json.dumps(
            {
                "hookName": "Stop",
                "sessionId": "ag-adapter-1",
                "transcript": [
                    {"type": "USER_INPUT", "content": "<USER_REQUEST>第一轮</USER_REQUEST>"},
                    {"type": "PLANNER_RESPONSE", "content": "第一轮回答"},
                    {"type": "USER_INPUT", "content": "<USER_REQUEST>第二轮</USER_REQUEST>"},
                    {"type": "PLANNER_RESPONSE", "content": "第二轮回答"},
                ],
            }
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert search.returncode == 0, search.stderr
    assert add.returncode == 0, add.stderr
    calls = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert calls[0]["payload"]["prompt"] == "原始用户问题"
    assert calls[1]["payload"]["prompt"] == "第二轮"
    assert calls[1]["payload"]["last_assistant_message"] == "第二轮回答"

    uninstall_hook("antigravity")


def test_antigravity_native_payload_fields_search_and_add(tmp_path):
    """Antigravity 2.9.x uses lastUserInput/finalModelOutput fields."""
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")

    search_result = run_payload(
        {
            "hook_event_name": "PreInvocation",
            "sessionId": "ag-session-1",
            "lastUserInput": "今天适合出门吗？",
        },
        agent="antigravity",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert "injectSteps" in search_result
    assert backend.search_calls == [
        (
            "今天适合出门吗？",
            {"user_id": "test-user", "conversation_id": "antigravity:ag-session-1"},
        )
    ]

    run_payload(
        {
            "hook_event_name": "Stop",
            "sessionId": "ag-session-1",
            "fullyIdle": True,
            "finalModelOutput": "今天很适合出门散步。",
        },
        agent="antigravity",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert backend.add_calls == [
        (
            [
                {"role": "user", "content": "今天适合出门吗？"},
                {"role": "assistant", "content": "今天很适合出门散步。"},
            ],
            {
                "user_id": "test-user",
                "conversation_id": "antigravity:ag-session-1",
                "async_mode": True,
            },
        )
    ]


def test_antigravity_prefers_canonical_transcript_user_input_over_augmented_last_user_input(tmp_path):
    """Runtime metadata appended to lastUserInput must not be stored as user text."""
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")
    augmented = (
        "晚上好\n"
        "The current local time is: 2026-08-24T20:04:29+08:00. "
        "The user changed setting `Model Selection` from None to Gemini 3.7 Flash (High)."
    )
    payload = {
        "hook_event_name": "PreInvocation",
        "sessionId": "ag-augmented-1",
        "lastUserInput": augmented,
        "transcript": [{"type": "USER_INPUT", "content": "晚上好"}],
    }

    run_payload(
        payload,
        agent="antigravity",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    assert backend.search_calls[0][0] == "晚上好"
    assert store.load("ag-augmented-1").prompt == "晚上好"


def test_antigravity_multiturn_prefers_latest_request_from_full_transcript(tmp_path):
    """A full transcript keeps each turn distinct when transcript.jsonl is stale."""
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")
    transcript = tmp_path / "transcript.jsonl"
    transcript_full = tmp_path / "transcript_full.jsonl"

    def write_transcript(prompt, answer):
        transcript_full.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "type": "USER_INPUT",
                            "content": f"<USER_REQUEST>{prompt}</USER_REQUEST><ADDITIONAL_METADATA>ignored",
                        }
                    ),
                    json.dumps({"type": "PLANNER_RESPONSE", "content": answer}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        # The hook points at transcript.jsonl; the parser must choose the
        # authoritative sibling transcript_full.jsonl instead.
        transcript.write_text(
            json.dumps({"type": "USER_INPUT", "content": "第一轮"}) + "\n",
            encoding="utf-8",
        )

    for prompt, answer in (("第一轮", "回答一"), ("第二轮", "回答二")):
        write_transcript(prompt, answer)
        run_payload(
            {
                "hook_event_name": "PreInvocation",
                "conversationId": "ag-multi-turn",
                "lastUserInput": "第一轮",
                "transcriptPath": str(transcript),
            },
            agent="antigravity",
            config_loader=config,
            backend_factory=lambda _: backend,
            store=store,
        )
        run_payload(
            {
                "hook_event_name": "Stop",
                "conversationId": "ag-multi-turn",
                "fullyIdle": True,
                "finalModelOutput": answer,
                "transcriptPath": str(transcript),
            },
            agent="antigravity",
            config_loader=config,
            backend_factory=lambda _: backend,
            store=store,
        )

    assert [call[0] for call in backend.search_calls] == ["第一轮", "第二轮"]
    assert [call[0][0]["content"] for call in backend.add_calls] == ["第一轮", "第二轮"]


def test_antigravity_stop_rechecks_transcript_instead_of_stale_search_state(tmp_path):
    """Stop should use the current transcript even if search state is old."""
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")
    run_payload(
        {
            "hook_event_name": "PreInvocation",
            "conversationId": "ag-stale-state",
            "lastUserInput": "第一轮",
        },
        agent="antigravity",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    run_payload(
        {
            "hook_event_name": "Stop",
            "conversationId": "ag-stale-state",
            "fullyIdle": True,
            "finalModelOutput": "第二轮回答",
            "transcript": [
                {"type": "USER_INPUT", "content": "<USER_REQUEST>第二轮</USER_REQUEST>"},
                {"type": "PLANNER_RESPONSE", "content": "第二轮回答"},
            ],
        },
        agent="antigravity",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert backend.add_calls[0][0] == [
        {"role": "user", "content": "第二轮"},
        {"role": "assistant", "content": "第二轮回答"},
    ]


def test_antigravity_transcript_user_input_and_planner_response(tmp_path):
    """Antigravity transcript records normalize to the common turn shape."""
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")
    transcript = [
        {"type": "USER_INPUT", "content": "用户的问题"},
        {"type": "PLANNER_RESPONSE", "content": "助手的最终回答"},
    ]

    run_payload(
        {
            "hook_event_name": "PreInvocation",
            "sessionId": "ag-transcript-1",
            "transcript": transcript,
        },
        agent="antigravity",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    run_payload(
        {
            "hook_event_name": "Stop",
            "sessionId": "ag-transcript-1",
            "fullyIdle": True,
            "transcript": transcript,
        },
        agent="antigravity",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )

    assert backend.search_calls[0][0] == "用户的问题"
    assert backend.add_calls[0][0] == [
        {"role": "user", "content": "用户的问题"},
        {"role": "assistant", "content": "助手的最终回答"},
    ]


def test_stop_without_fully_idle_field_still_stores_for_other_agents(tmp_path):
    backend = FakeBackend()
    store = HookStateStore(tmp_path / "state")
    run_payload(
        {"hook_event_name": "PreInvocation", "session_id": "s1", "prompt": "raw user"},
        agent="antigravity",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    run_payload(
        {"hook_event_name": "Stop", "session_id": "s1", "lastAssistantMessage": "final answer"},
        agent="antigravity",
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert len(backend.add_calls) == 1


def test_runner_stdin_malformed_json_is_json_on_stdout(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("{"))
    run_stdin()
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {}
    assert "invalid hook payload" in captured.err
