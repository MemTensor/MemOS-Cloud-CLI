from __future__ import annotations

import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from memos_cli.hooks import codex
from memos_cli.hooks.installer import HookConfigError, install_codex_hook, is_managed_hook, uninstall_codex_hook
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


def config():
    return SimpleNamespace(defaults=SimpleNamespace(user_id="test-user", framework=None))


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
    state = store.load("s1")
    assert state is not None
    assert state.conversation_id == "codex:s1"
    assert state.prompt == "remember this"


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
        {"user_id": "test-user", "conversation_id": "codex:s1", "agent_id": "codex", "async_mode": True},
    )]
    assert store.load("s1", "t1") is None
    run_payload(
        {"hook_event_name": "Stop", "sessionId": "s1", "turnId": "t1", "lastAssistantMessage": "duplicate"},
        config_loader=config,
        backend_factory=lambda _: backend,
        store=store,
    )
    assert len(backend.add_calls) == 1


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
        install_codex_hook()
        install_codex_hook()
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
    uninstall_codex_hook()
    uninstalled = json.loads(config_path.read_text())
    assert uninstalled == {"other": {"x": 1}, "hooks": {"UserPromptSubmit": [matched_entry]}}


def test_installer_rejects_malformed_json(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "hooks.json").write_text("not json")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    with patch("memos_cli.hooks.installer._resolve_memos_executable", return_value=tmp_path / "memos"):
        with pytest.raises(HookConfigError):
            install_codex_hook()


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
        install_codex_hook()
    assert set(json.loads(config_path.read_text())["hooks"]) == {"UserPromptSubmit", "Stop"}


def test_runner_stdin_malformed_json_is_json_on_stdout(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("{"))
    run_stdin()
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {}
    assert "invalid hook payload" in captured.err
