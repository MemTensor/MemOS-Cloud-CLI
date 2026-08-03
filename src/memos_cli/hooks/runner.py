"""Fail-open Codex hook runner."""
from __future__ import annotations

import json
import sys
from typing import Any, Callable

from memos_cli.backend.memos_api import get_backend
from memos_cli.config import load_config
from memos_cli.state import set_runtime_options

from .codex import (
    CODEX_AGENT,
    STOP_EVENT,
    USER_PROMPT_EVENT,
    conversation_id_for,
    event_name,
    extract_final_answer,
    extract_prompt,
    host_turn_id,
    is_cancelled,
    memory_context,
    prompt_response,
    session_key,
    stop_response,
    workspace_path,
)
from .state_store import HookStateStore, HookTurnState


def _diagnose(message: str) -> None:
    print(f"[memos hook] {message}", file=sys.stderr, flush=True)


def _emit(response: dict[str, Any]) -> dict[str, Any]:
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
    return response


def run_payload(
    payload: dict[str, Any],
    *,
    config_loader: Callable[[], Any] | None = None,
    backend_factory: Callable[[Any], Any] | None = None,
    store: HookStateStore | None = None,
) -> dict[str, Any]:
    """Process one decoded Codex payload and return the host response."""
    store = store or HookStateStore()
    config_loader = config_loader or load_config
    backend_factory = backend_factory or get_backend
    event = event_name(payload)
    if event == USER_PROMPT_EVENT:
        prompt = extract_prompt(payload)
        if not prompt:
            return prompt_response("")

        key = session_key(payload)
        turn_id = host_turn_id(payload)
        conversation_id = conversation_id_for(payload)
        state = HookTurnState.create(
            session_key=key,
            conversation_id=conversation_id,
            prompt=prompt,
            host_turn_id=turn_id,
            workspace_path=workspace_path(payload),
        )
        try:
            store.save(state)
        except Exception:
            _diagnose("could not persist turn state; continuing")

        context = ""
        try:
            config = config_loader()
            set_runtime_options(framework=CODEX_AGENT)
            if getattr(config, "defaults", None) is not None:
                config.defaults.framework = CODEX_AGENT
            backend = backend_factory(config)
            result = backend.search_memories(
                prompt,
                user_id=config.defaults.user_id,
                conversation_id=conversation_id,
                agent_id=CODEX_AGENT,
            )
            context = memory_context(result)
        except Exception:
            _diagnose("memory retrieval failed; continuing")
        return prompt_response(context)

    if event == STOP_EVENT:
        key = session_key(payload)
        state = None
        try:
            turn_id = host_turn_id(payload)
            state = store.load(key, turn_id)
            if state and turn_id and state.host_turn_id != turn_id:
                state = None
            if state and not is_cancelled(payload):
                final_answer = extract_final_answer(payload, workspace_override=state.workspace_path)
                if final_answer.strip() and state.prompt.strip():
                    try:
                        config = config_loader()
                        set_runtime_options(framework=CODEX_AGENT)
                        if getattr(config, "defaults", None) is not None:
                            config.defaults.framework = CODEX_AGENT
                        backend = backend_factory(config)
                        backend.add_memory(
                            [
                                {"role": "user", "content": state.prompt},
                                {"role": "assistant", "content": final_answer},
                            ],
                            user_id=config.defaults.user_id,
                            conversation_id=state.conversation_id,
                            agent_id=CODEX_AGENT,
                            async_mode=True,
                        )
                    except Exception:
                        _diagnose("memory save failed; continuing")
        except Exception:
            _diagnose("could not process turn state; continuing")
        finally:
            if state is not None:
                try:
                    store.delete(key, turn_id)
                except Exception:
                    _diagnose("could not clean turn state; continuing")
        return stop_response()

    return {}


def run_stdin() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except Exception:
        _diagnose("invalid hook payload; continuing")
        return _emit({})
    try:
        return _emit(run_payload(payload))
    except Exception:
        _diagnose("hook failed; continuing")
        return _emit({})


main = run_stdin


if __name__ == "__main__":
    run_stdin()
