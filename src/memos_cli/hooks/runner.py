"""Fail-open native host hook runner."""
from __future__ import annotations

import json
import sys
from typing import Any, Callable

from memos_cli.backend.memos_api import get_backend
from memos_cli.config import load_config
from memos_cli.state import set_runtime_options

from .agents import DEFAULT_HOOK_AGENT, HookAgentSpec, get_hook_agent_spec
from .payload import (
    conversation_id_for,
    event_name,
    extract_final_answer,
    extract_prompt,
    extract_transcript_prompt,
    extract_transformed_prompt,
    host_turn_id,
    is_cancelled,
    is_fully_idle,
    memory_context,
    session_key,
    workspace_path,
)
from .state_store import HookStateStore, HookTurnState


def _diagnose(message: str) -> None:
    print(f"[memos hook] {message}", file=sys.stderr, flush=True)


def _emit(response: dict[str, Any]) -> dict[str, Any]:
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
    return response


def _event_matches(event: str | None, expected: str, aliases: tuple[str, ...] = ()) -> bool:
    normalized = (event or "").strip().lower()
    if not normalized:
        return False
    if normalized == expected.strip().lower():
        return True
    return normalized in {alias.strip().lower() for alias in aliases}


def _hook_scope_kwargs(config: Any, conversation_id: str, agent: str) -> dict[str, Any]:
    """Build hook memory scope without requiring multi-view projects."""
    defaults = getattr(config, "defaults", None)
    kwargs: dict[str, Any] = {
        "user_id": getattr(defaults, "user_id", None),
        "conversation_id": conversation_id,
    }
    if getattr(defaults, "multi_view_enabled", False):
        kwargs["agent_id"] = getattr(defaults, "agent_id", None) or agent
    return kwargs


def _prompt_response(context: str, spec: HookAgentSpec, payload: dict[str, Any]) -> dict[str, Any]:
    """Format search output for the host hook protocol."""
    if not context:
        return _allow_response(spec)
    if spec.response_style == "codex":
        return {
            "hookSpecificOutput": {
                "hookEventName": spec.search_event,
                "additionalContext": context,
            }
        }
    if spec.response_style == "cursor":
        return {"continue": True}
    if spec.response_style == "copilot":
        transformed_prompt = extract_transformed_prompt(payload, agent=spec.agent)
        if transformed_prompt.strip():
            return {"modifiedTransformedPrompt": f"{context}\n\n{transformed_prompt}"}
        return {"modifiedTransformedPrompt": context}
    if spec.response_style == "antigravity":
        return {"injectSteps": [{"ephemeralMessage": context}]}
    if spec.response_style == "hermes":
        return {"context": context}
    if spec.response_style == "openclaw":
        return {"prependContext": context}
    if spec.response_style == "cline":
        return {"cancel": False, "contextModification": context}
    return {
        "continue": True,
        "additionalContext": context,
        "context": context,
    }


def _stop_response(spec: HookAgentSpec) -> dict[str, Any]:
    """Format add/stop output for the host hook protocol."""
    if spec.response_style == "codex":
        return {"continue": True, "suppressOutput": True}
    return _allow_response(spec)


def _allow_response(spec: HookAgentSpec) -> dict[str, Any]:
    if spec.response_style == "cursor":
        return {"continue": True}
    return {}


def run_payload(
    payload: dict[str, Any],
    *,
    agent: str = DEFAULT_HOOK_AGENT,
    fallback_event: str | None = None,
    config_loader: Callable[[], Any] | None = None,
    backend_factory: Callable[[Any], Any] | None = None,
    store: HookStateStore | None = None,
) -> dict[str, Any]:
    """Process one decoded native-hook payload and return the host response."""
    spec = get_hook_agent_spec(agent)
    store = store or HookStateStore(agent=spec.agent)
    config_loader = config_loader or load_config
    backend_factory = backend_factory or get_backend
    event = event_name(payload, fallback_event)
    if not spec.search_hook_enabled and _event_matches(event, spec.search_event, spec.search_aliases):
        return _allow_response(spec)
    phase = spec.event_phase(event)
    if phase == "search":
        prompt = extract_prompt(payload, agent=spec.agent)
        if not prompt:
            return _allow_response(spec)

        key = session_key(payload)
        turn_id = host_turn_id(payload)
        conversation_id = conversation_id_for(payload, spec.agent)
        state = HookTurnState.create(
            agent=spec.agent,
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

        if not spec.search_injection_enabled:
            return _allow_response(spec)

        context = ""
        try:
            config = config_loader()
            set_runtime_options(framework=spec.agent)
            if getattr(config, "defaults", None) is not None:
                config.defaults.framework = spec.agent
            backend = backend_factory(config)
            result = backend.search_memories(
                prompt,
                **_hook_scope_kwargs(config, conversation_id, spec.agent),
            )
            context = memory_context(result)
        except Exception as exc:
            _diagnose(f"memory retrieval failed ({type(exc).__name__}): {exc}; continuing")
        return _prompt_response(context, spec, payload)

    if phase == "add":
        if spec.add_requires_fully_idle and not is_fully_idle(payload):
            # Background tasks still running; a later Stop with fullyIdle=true
            # will store this turn, so keep the saved turn state untouched.
            return _stop_response(spec)
        key = session_key(payload)
        state = None
        conversation_id = conversation_id_for(payload, spec.agent)
        try:
            turn_id = host_turn_id(payload)
            # Claim the pending prompt before making the remote request. Cline
            # can deliver the same completion through its AgentPlugin and its
            # IDE TaskComplete hook, and it retries a timed-out plugin call.
            # An atomic consume ensures only one of those processes can save
            # the turn.
            state = store.consume(key, turn_id)
            if state and turn_id and state.host_turn_id != turn_id:
                state = None
            # Cursor's afterAgentResponse payload contains only the assistant
            # text. Cline's completion callback can also be duplicated by its
            # AgentPlugin + IDE TaskComplete surfaces. Once the pending state
            # is consumed, never treat the payload as a new user prompt.
            if spec.agent in {"cursor", "cline"} and state is None:
                return _stop_response(spec)
            if spec.agent == "antigravity":
                # Stop carries the authoritative transcript path. Re-read the
                # latest USER_INPUT here so a stale/missed PreInvocation state
                # cannot make every later turn reuse turn one.
                prompt = extract_transcript_prompt(payload, agent=spec.agent)
                if not prompt.strip():
                    prompt = state.prompt if state is not None else extract_prompt(payload, agent=spec.agent)
            else:
                prompt = state.prompt if state is not None else extract_prompt(payload, agent=spec.agent)
            workspace_override = state.workspace_path if state is not None else None
            if not is_cancelled(payload):
                final_answer = extract_final_answer(
                    payload,
                    workspace_override=workspace_override,
                    agent=spec.agent,
                )
                if spec.agent == "copilot" and not final_answer.strip():
                    _diagnose(
                        "Copilot agentStop did not yield an assistant message from transcriptPath "
                        "or the session-state fallback"
                    )
                if final_answer.strip() and prompt.strip():
                    try:
                        config = config_loader()
                        set_runtime_options(framework=spec.agent)
                        if getattr(config, "defaults", None) is not None:
                            config.defaults.framework = spec.agent
                        backend = backend_factory(config)
                        backend.add_memory(
                            [
                                {"role": "user", "content": prompt},
                                {"role": "assistant", "content": final_answer},
                            ],
                            **_hook_scope_kwargs(config, state.conversation_id if state is not None else conversation_id, spec.agent),
                            async_mode=True,
                        )
                    except Exception as exc:
                        _diagnose(f"memory save failed ({type(exc).__name__}): {exc}; continuing")
                elif state is not None:
                    # Do not lose the pending prompt when a host transcript is
                    # not readable yet or an older host omits the final
                    # response. A later completion callback can retry
                    # extraction; successful add still consumes it once.
                    try:
                        store.save(state)
                    except Exception:
                        _diagnose("could not restore pending turn state")
        except Exception as exc:
            _diagnose(f"could not process turn state ({type(exc).__name__}): {exc}; continuing")
        return _stop_response(spec)

    return {}


def run_stdin(agent: str = DEFAULT_HOOK_AGENT, event: str | None = None) -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except Exception:
        _diagnose("invalid hook payload; continuing")
        return _emit({})
    try:
        return _emit(run_payload(payload, agent=agent, fallback_event=event))
    except Exception:
        _diagnose("hook failed; continuing")
        return _emit({})


main = run_stdin


if __name__ == "__main__":
    run_stdin()
