"""Safe, idempotent Codex hooks.json installation."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import Any

from memos_cli.executable import resolve_memos_executable as _resolve_memos_executable
from .state_store import HookStateStore

MANAGED_MARKER = "memos hook run --agent codex"
MANAGED_COMMAND_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])memos(?:\.exe|\.js)?['\"]?\s+hook run --agent codex(?:\s|$)"
)
HOOK_EVENTS = ("UserPromptSubmit", "Stop")


class HookConfigError(ValueError):
    """Invalid or unavailable Codex hook configuration."""


def codex_home() -> Path:
    return Path(os.getenv("CODEX_HOME", "~/.codex")).expanduser()


def hooks_path() -> Path:
    return codex_home() / "hooks.json"


def is_managed_hook(hook: Any) -> bool:
    command = str(hook.get("command", "")) if isinstance(hook, dict) else ""
    return bool(MANAGED_COMMAND_PATTERN.search(command))


def _read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise HookConfigError(f"Unable to read Codex hooks configuration: {path}") from exc
    if not isinstance(data, dict):
        raise HookConfigError("Codex hooks configuration must be a JSON object")
    return data


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _managed_hook(command: str, event: str) -> dict[str, Any]:
    return {
        "type": "command",
        "command": command,
        "timeout": 60,
        "statusMessage": "Retrieving MemOS memory" if event == "UserPromptSubmit" else "Saving MemOS memory",
    }


def _event_hooks(config: dict[str, Any], event: str) -> list[Any]:
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise HookConfigError("Codex hooks field must be a JSON object")
    current = hooks.get(event)
    if current is None:
        current = []
        hooks[event] = current
    if not isinstance(current, list):
        raise HookConfigError(f"Codex {event} hooks field must be an array")
    return current


def _append_managed(event_entries: list[Any], hook: dict[str, Any]) -> None:
    event_entries[:] = _remove_managed(event_entries)
    event_entries.append({"hooks": [hook]})


def _remove_managed(event_entries: list[Any]) -> list[Any]:
    updated: list[Any] = []
    for entry in event_entries:
        if is_managed_hook(entry):
            continue
        if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
            updated.append(entry)
            continue
        original_hooks = entry["hooks"]
        managed_found = any(is_managed_hook(item) for item in original_hooks)
        if not managed_found:
            updated.append(entry)
            continue
        remaining = [item for item in original_hooks if not is_managed_hook(item)]
        if remaining:
            entry["hooks"] = remaining
            updated.append(entry)
    return updated


def resolve_command() -> str:
    resolved = _resolve_memos_executable()
    if resolved is None:
        raise HookConfigError("Unable to resolve the installed memos executable")
    executable = Path(resolved)
    command_prefix = shlex.quote(str(executable))
    if executable.suffix.lower() == ".js" and not os.access(executable, os.X_OK):
        node = shutil.which("node")
        if node:
            command_prefix = f"{shlex.quote(str(Path(node).resolve()))} {command_prefix}"
    return f"{command_prefix} hook run --agent codex"


def install_codex_hook() -> Path:
    path = hooks_path()
    config = _read_config(path)
    command = resolve_command()
    for event in HOOK_EVENTS:
        entries = _event_hooks(config, event)
        _append_managed(entries, _managed_hook(command, event))
    _atomic_write(path, config)
    return path


install_codex_hooks = install_codex_hook


def uninstall_codex_hook() -> Path | None:
    path = hooks_path()
    try:
        if path.exists():
            config = _read_config(path)
            hooks = config.get("hooks")
            if isinstance(hooks, dict):
                for event in HOOK_EVENTS:
                    entries = hooks.get(event)
                    if isinstance(entries, list):
                        updated = _remove_managed(entries)
                        if updated:
                            hooks[event] = updated
                        else:
                            hooks.pop(event, None)
                if not hooks:
                    config.pop("hooks", None)
                _atomic_write(path, config)
    finally:
        HookStateStore().clear()
    return path if path.exists() else None


uninstall_codex_hooks = uninstall_codex_hook
