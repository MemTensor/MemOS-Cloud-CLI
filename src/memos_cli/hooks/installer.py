"""Safe, idempotent native hook installation."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from memos_cli.executable import resolve_memos_executable as _resolve_memos_executable

from .agents import DEFAULT_HOOK_AGENT, HookAgentSpec, HookConfigError, get_hook_agent_spec, hook_agent_names
from .host_templates import (
    antigravity_hook_adapter,
    cline_plugin,
    cline_plugin_package_json,
    deepseek_plugin,
    hermes_plugin_entry,
    hermes_plugin_manifest,
    openclaw_plugin_entry,
    openclaw_plugin_manifest,
    openclaw_plugin_package_json,
    opencode_plugin,
)
from .state_store import HookStateStore

MANAGED_MARKER = "memos hook run --agent"
HOOK_TIMEOUT_SECONDS = 60
ANTIGRAVITY_HOOK_NAME = "memos-memory"
COPILOT_HOOK_FILENAME = "memos-memory.json"
HERMES_PLUGIN_NAME = "memos-memory"
CLINE_IDE_HOOK_EVENTS = ("UserPromptSubmit", "TaskComplete")
ANTIGRAVITY_ADAPTER_FILENAME = "memos-antigravity-hook-adapter.py"
ANTIGRAVITY_ADAPTER_MARKER = "antigravity payload adapter"


def _hook_command_agent(command: str) -> str | None:
    try:
        parts = shlex.split(command)
    except ValueError:
        return None

    for index, part in enumerate(parts):
        if Path(part).name.lower() == ANTIGRAVITY_ADAPTER_FILENAME:
            return "antigravity"
        if Path(part).name.lower() not in {"memos", "memos.exe", "memos.js"}:
            continue
        if index + 2 >= len(parts) or parts[index + 1 : index + 3] != ["hook", "run"]:
            continue
        tail = parts[index + 3 :]
        for option_index, option in enumerate(tail):
            if option == "--agent" and option_index + 1 < len(tail):
                return tail[option_index + 1].strip().lower()
            if option.startswith("--agent="):
                return option.split("=", 1)[1].strip().lower()
    return None


def is_managed_hook(hook: Any, agent: str | None = None) -> bool:
    """Return whether a hook command belongs to MemOS native hooks."""
    command = str(hook.get("command", "")) if isinstance(hook, dict) else ""
    hook_agent = _hook_command_agent(command)
    if not hook_agent:
        return False
    if agent is not None:
        return hook_agent == get_hook_agent_spec(agent).agent
    return hook_agent in set(hook_agent_names())


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise HookConfigError(f"Unable to read hook configuration: {path}") from exc


def _read_json_config(path: Path) -> dict[str, Any]:
    raw = _read_text_file(path)
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HookConfigError(f"Unable to read hook JSON configuration: {path}") from exc
    if not isinstance(data, dict):
        raise HookConfigError(f"Hook configuration must be a JSON object: {path}")
    return data


def _read_yaml_config(path: Path) -> dict[str, Any]:
    raw = _read_text_file(path)
    if not raw.strip():
        return {}
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise HookConfigError(f"Unable to read hook YAML configuration: {path}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise HookConfigError(f"Hook configuration must be a YAML object: {path}")
    return data


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, mode)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _atomic_write_yaml(path: Path, data: dict[str, Any]) -> None:
    _atomic_write_text(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


def _event_status_message(phase: str) -> str:
    return "Retrieving MemOS memory" if phase == "search" else "Saving MemOS memory"


def _managed_hook(
    command: str,
    phase: str,
    *,
    include_type: bool = True,
    include_status_message: bool = True,
) -> dict[str, Any]:
    hook: dict[str, Any] = {
        "command": command,
        "timeout": HOOK_TIMEOUT_SECONDS,
    }
    if include_status_message:
        hook["statusMessage"] = _event_status_message(phase)
    if include_type:
        hook = {"type": "command", **hook}
    return hook


def _read_config(path: Path, spec: HookAgentSpec) -> dict[str, Any]:
    if spec.config_format == "generic_yaml":
        return _read_yaml_config(path)
    return _read_json_config(path)


def _write_config(path: Path, spec: HookAgentSpec, config: dict[str, Any]) -> None:
    if spec.config_format == "generic_yaml":
        _atomic_write_yaml(path, config)
    else:
        _atomic_write_json(path, config)


def _event_hooks(config: dict[str, Any], event: str, spec: HookAgentSpec) -> list[Any]:
    if spec.config_layout == "antigravity":
        root = config.setdefault(ANTIGRAVITY_HOOK_NAME, {})
        if not isinstance(root, dict):
            raise HookConfigError(f"{spec.display_name} hook root must be an object")
        current = root.get(event)
        if current is None:
            current = []
            root[event] = current
        if not isinstance(current, list):
            raise HookConfigError(f"{spec.display_name} {event} hooks field must be an array")
        return current

    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise HookConfigError(f"{spec.display_name} hooks field must be an object")
    current = hooks.get(event)
    if current is None:
        current = []
        hooks[event] = current
    if not isinstance(current, list):
        raise HookConfigError(f"{spec.display_name} {event} hooks field must be an array")
    return current


def _remove_managed(event_entries: list[Any], spec: HookAgentSpec) -> list[Any]:
    updated: list[Any] = []
    for entry in event_entries:
        if is_managed_hook(entry, spec.agent):
            continue
        if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
            updated.append(entry)
            continue
        original_hooks = entry["hooks"]
        managed_found = any(is_managed_hook(item, spec.agent) for item in original_hooks)
        if not managed_found:
            updated.append(entry)
            continue
        remaining = [item for item in original_hooks if not is_managed_hook(item, spec.agent)]
        if remaining:
            entry["hooks"] = remaining
            updated.append(entry)
    return updated


def _append_wrapped_command_hook(config: dict[str, Any], spec: HookAgentSpec, event: str, hook: dict[str, Any]) -> None:
    entries = _event_hooks(config, event, spec)
    entries[:] = _remove_managed(entries, spec)
    entries.append({"hooks": [hook]})


def _append_direct_command_hook(config: dict[str, Any], spec: HookAgentSpec, event: str, hook: dict[str, Any]) -> None:
    entries = _event_hooks(config, event, spec)
    entries[:] = _remove_managed(entries, spec)
    entries.append(hook)


def _remove_event(config: dict[str, Any], spec: HookAgentSpec, event: str) -> None:
    if spec.config_layout == "antigravity":
        root = config.get(ANTIGRAVITY_HOOK_NAME)
        if not isinstance(root, dict):
            return
        entries = root.get(event)
        if not isinstance(entries, list):
            return
        updated = _remove_managed(entries, spec)
        if updated:
            root[event] = updated
        else:
            root.pop(event, None)
        if not root or (set(root) == {"enabled"}):
            config.pop(ANTIGRAVITY_HOOK_NAME, None)
        return

    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        return
    entries = hooks.get(event)
    if not isinstance(entries, list):
        return
    updated = _remove_managed(entries, spec)
    if updated:
        hooks[event] = updated
    else:
        hooks.pop(event, None)
    if not hooks:
        config.pop("hooks", None)


def _remove_stale_managed_events(config: dict[str, Any], spec: HookAgentSpec) -> None:
    """Remove MemOS hooks left under retired event names.

    Cursor has both ``stop`` and ``afterAgentResponse``. Older MemOS builds
    used the former for capture; when the event mapping changed, simply
    appending the new hook left both managed commands active and stored every
    turn twice. Keep unrelated user hooks intact and remove only managed
    commands from non-current event keys.
    """
    canonical = {_normalize_event_name(event) for event in spec.events}

    if spec.config_layout == "antigravity":
        root = config.get(ANTIGRAVITY_HOOK_NAME)
        if not isinstance(root, dict):
            return
        event_map = root
    else:
        event_map = config.get("hooks")
        if not isinstance(event_map, dict):
            return

    for event in list(event_map):
        if event == "enabled" or _normalize_event_name(str(event)) in canonical:
            continue
        entries = event_map.get(event)
        if not isinstance(entries, list):
            continue
        updated = _remove_managed(entries, spec)
        if updated:
            event_map[event] = updated
        else:
            event_map.pop(event, None)

    if spec.config_layout == "antigravity":
        if not root or set(root) == {"enabled"}:
            config.pop(ANTIGRAVITY_HOOK_NAME, None)
    elif not event_map:
        config.pop("hooks", None)


def _normalize_event_name(event: str) -> str:
    return event.strip().lower()


def _resolve_command_prefix() -> str:
    resolved = _resolve_memos_executable()
    if resolved is None:
        raise HookConfigError("Unable to resolve the installed memos executable")
    executable = Path(resolved)
    command_prefix = shlex.quote(str(executable))
    if executable.suffix.lower() == ".js" and not os.access(executable, os.X_OK):
        node = shutil.which("node")
        if node:
            command_prefix = f"{shlex.quote(str(Path(node).resolve()))} {command_prefix}"
    return command_prefix


def resolve_command(agent: str = DEFAULT_HOOK_AGENT, event: str | None = None) -> str:
    """Return the native hook command for a target agent and optional event."""
    spec = get_hook_agent_spec(agent)
    command = f"{_resolve_command_prefix()} hook run --agent {shlex.quote(spec.agent)}"
    if event:
        command = f"{command} --event {shlex.quote(event)}"
    return command


def _portable_command(agent: str = DEFAULT_HOOK_AGENT, event: str | None = None) -> str:
    """Return a PATH-based hook command for configs that must run off-machine."""
    spec = get_hook_agent_spec(agent)
    command = f"memos hook run --agent {shlex.quote(spec.agent)}"
    if event:
        command = f"{command} --event {shlex.quote(event)}"
    return command


def _resolve_command_argv(agent: str) -> list[str]:
    """Return the hook command as argv for generated JS wrappers."""
    return shlex.split(resolve_command(agent))


def _antigravity_adapter_path(spec: HookAgentSpec) -> Path:
    return spec.config_path().parent / ANTIGRAVITY_ADAPTER_FILENAME


def _antigravity_adapter_python() -> str:
    """Resolve a Python interpreter for the small local payload adapter."""
    return shutil.which("python3") or shutil.which("python") or "/usr/bin/python3"


def _install_antigravity_adapter(spec: HookAgentSpec) -> Path:
    path = _antigravity_adapter_path(spec)
    if path.exists() and ANTIGRAVITY_ADAPTER_MARKER not in _read_text_file(path):
        raise HookConfigError(f"Refusing to overwrite a user-owned Antigravity adapter: {path}")
    _atomic_write_text(path, antigravity_hook_adapter(_resolve_command_argv(spec.agent), spec))
    if os.name != "nt":
        path.chmod(path.stat().st_mode | 0o700)
    return path


def _antigravity_adapter_command(spec: HookAgentSpec, event: str) -> str:
    adapter = shlex.quote(str(_antigravity_adapter_path(spec)))
    python = shlex.quote(_antigravity_adapter_python())
    return f"{python} {adapter} --event {shlex.quote(event)}"


def _deepseek_patch_path(spec: HookAgentSpec) -> Path:
    """Return the home-level cordis.patch.yml that registers dsh plugins."""
    return spec.config_path().parent.parent / "cordis.patch.yml"


def _set_deepseek_plugin_registered(spec: HookAgentSpec, registered: bool) -> None:
    """Insert or remove the managed plugin row in ~/.dsh/cordis.patch.yml."""
    patch_path = _deepseek_patch_path(spec)
    raw = _read_text_file(patch_path)
    try:
        patch = yaml.safe_load(raw) if raw.strip() else []
    except yaml.YAMLError as exc:
        raise HookConfigError(f"Unable to read dsh patch configuration: {patch_path}") from exc
    if patch is None:
        patch = []
    if not isinstance(patch, list):
        raise HookConfigError(f"dsh patch configuration must be a YAML array: {patch_path}")

    plugin_path = str(spec.config_path())

    def _is_managed_row(row: Any) -> bool:
        return isinstance(row, dict) and row.get("id") == ANTIGRAVITY_HOOK_NAME

    for operation in patch:
        if isinstance(operation, dict) and isinstance(operation.get("insert"), list):
            operation["insert"] = [row for row in operation["insert"] if not _is_managed_row(row)]
    patch = [
        operation
        for operation in patch
        if not (isinstance(operation, dict) and operation.get("insert") == [])
    ]
    if registered:
        patch.append({"insert": [{"id": ANTIGRAVITY_HOOK_NAME, "name": plugin_path}]})
    _atomic_write_yaml_list(patch_path, patch)


def _atomic_write_yaml_list(path: Path, data: list[Any]) -> None:
    _atomic_write_text(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


def _cline_ide_hooks_dir() -> Path:
    """Return the global hook directory used by Cline IDE extensions."""
    return Path.home() / "Documents" / "Cline" / "Hooks"


def _cline_ide_hook_path(event: str) -> Path:
    suffix = ".ps1" if os.name == "nt" else ""
    return _cline_ide_hooks_dir() / f"{event}{suffix}"


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _cline_ide_hook_content(argv: list[str], event: str) -> str:
    """Build a transparent stdin/stdout wrapper for one Cline IDE hook."""
    command = [*argv, "--event", event]
    marker = "# Managed by MemOS CLI: memos hook run --agent cline"
    if os.name == "nt":
        executable, *args = command
        rendered_args = " ".join(_powershell_quote(arg) for arg in args)
        return f"{marker}\n& {_powershell_quote(executable)} {rendered_args}\nexit $LASTEXITCODE\n"
    rendered = " ".join(shlex.quote(arg) for arg in command)
    return f"#!/bin/sh\n{marker}\nexec {rendered}\n"


def _validate_cline_ide_hook_targets() -> None:
    for event in CLINE_IDE_HOOK_EVENTS:
        path = _cline_ide_hook_path(event)
        if not path.exists():
            continue
        content = _read_text_file(path)
        if MANAGED_MARKER not in content:
            raise HookConfigError(f"Refusing to overwrite a user-owned Cline hook: {path}")


def _install_cline_ide_hooks(argv: list[str]) -> tuple[Path, ...]:
    """Install executable UserPromptSubmit/TaskComplete hooks for Cline IDE."""
    _validate_cline_ide_hook_targets()
    installed: list[Path] = []
    for event in CLINE_IDE_HOOK_EVENTS:
        path = _cline_ide_hook_path(event)
        _atomic_write_text(path, _cline_ide_hook_content(argv, event))
        if os.name != "nt":
            path.chmod(path.stat().st_mode | 0o700)
        installed.append(path)
    return tuple(installed)


def _uninstall_cline_ide_hooks() -> bool:
    """Remove only MemOS-managed Cline IDE hook scripts."""
    removed = False
    for event in CLINE_IDE_HOOK_EVENTS:
        path = _cline_ide_hook_path(event)
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if MANAGED_MARKER not in content:
            continue
        path.unlink()
        removed = True
    return removed


def _cline_managed_install_roots(plugin_root: Path) -> set[Path]:
    """Find stale `cline plugin install` copies containing the MemOS marker."""
    installs_root = plugin_root / "_installed"
    if not installs_root.is_dir():
        return set()
    roots: set[Path] = set()
    for candidate in installs_root.rglob("*"):
        if not candidate.is_file() or candidate.is_symlink():
            continue
        if candidate.suffix.lower() not in {".js", ".ts", ".mjs", ".cjs"}:
            continue
        try:
            if candidate.stat().st_size > 1_000_000:
                continue
        except OSError:
            continue
        try:
            content = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if MANAGED_MARKER not in content:
            continue
        relative_parts = candidate.relative_to(installs_root).parts
        if len(relative_parts) < 3:
            continue
        depth = 3 if relative_parts[0] == "git" else 2
        if len(relative_parts) <= depth:
            continue
        roots.add(installs_root.joinpath(*relative_parts[:depth]))
    return roots


def _remove_stale_cline_managed_installs(plugin_root: Path) -> bool:
    removed = False
    for root in _cline_managed_install_roots(plugin_root):
        if root.is_dir():
            shutil.rmtree(root)
            removed = True
    return removed


def _install_plugin_js(spec: HookAgentSpec) -> Path:
    """Install the generated JS plugin file (OpenCode / Cline / DeepSeek)."""
    plugin_path = spec.config_path()
    argv = _resolve_command_argv(spec.agent)
    if spec.agent == "cline":
        _validate_cline_ide_hook_targets()
        entry = plugin_path / "index.js"
        legacy_entry = plugin_path.parent / "memos-memory.js"
        if plugin_path.exists() and not plugin_path.is_dir():
            raise HookConfigError(f"Cline plugin path is not a directory: {plugin_path}")
        if entry.exists() and MANAGED_MARKER not in _read_text_file(entry):
            raise HookConfigError(f"Refusing to overwrite a user-owned Cline plugin: {plugin_path}")
        if legacy_entry.exists() and MANAGED_MARKER not in _read_text_file(legacy_entry):
            raise HookConfigError(f"Refusing to replace a user-owned legacy Cline plugin: {legacy_entry}")
        _remove_stale_cline_managed_installs(plugin_path.parent)
        plugin_path.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(plugin_path / "package.json", cline_plugin_package_json())
        _atomic_write_text(entry, cline_plugin(argv, spec))
        if legacy_entry.exists():
            legacy_entry.unlink()
        _install_cline_ide_hooks(argv)
        return plugin_path
    elif spec.agent == "deepseek":
        content = deepseek_plugin(argv, spec)
    else:
        content = opencode_plugin(argv, spec)
    _atomic_write_text(plugin_path, content)
    if spec.agent == "deepseek":
        _set_deepseek_plugin_registered(spec, True)
    return plugin_path


def _uninstall_plugin_js(spec: HookAgentSpec) -> bool:
    """Remove the generated JS plugin when it is MemOS-managed."""
    if spec.agent == "cline":
        removed = _uninstall_cline_ide_hooks()
        plugin_dir = spec.config_path()
        entry = plugin_dir / "index.js"
        if entry.is_file() and MANAGED_MARKER in _read_text_file(entry):
            shutil.rmtree(plugin_dir)
            removed = True
        legacy_entry = plugin_dir.parent / "memos-memory.js"
        if legacy_entry.is_file() and MANAGED_MARKER in _read_text_file(legacy_entry):
            legacy_entry.unlink()
            removed = True
        removed = _remove_stale_cline_managed_installs(plugin_dir.parent) or removed
        return removed

    removed = False
    plugin_path = spec.config_path()
    if not plugin_path.is_file():
        return removed
    try:
        content = plugin_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return removed
    if MANAGED_MARKER not in content:
        return removed
    plugin_path.unlink()
    removed = True
    if spec.agent == "deepseek":
        try:
            _set_deepseek_plugin_registered(spec, False)
        except HookConfigError:
            pass
    return removed


def _hermes_config_path(spec: HookAgentSpec) -> Path:
    """Return the config that controls Hermes user-plugin enablement."""
    return spec.config_path().parent.parent / "config.yaml"


def _hermes_plugin_is_managed(plugin_dir: Path) -> bool:
    entry = plugin_dir / "__init__.py"
    if not entry.is_file():
        return False
    try:
        return MANAGED_MARKER in entry.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def _set_hermes_plugin_enabled(config: dict[str, Any], *, enabled: bool) -> None:
    """Update plugins.enabled without disturbing unrelated Hermes plugins."""
    plugins = config.get("plugins")
    if plugins is None:
        if not enabled:
            return
        plugins = {}
        config["plugins"] = plugins
    if not isinstance(plugins, dict):
        raise HookConfigError("Hermes plugins configuration must be an object")

    enabled_plugins = plugins.get("enabled")
    if enabled_plugins is None:
        if not enabled:
            return
        enabled_plugins = []
    if not isinstance(enabled_plugins, list):
        raise HookConfigError("Hermes plugins.enabled must be an array")
    enabled_plugins = [item for item in enabled_plugins if item != HERMES_PLUGIN_NAME]
    if enabled:
        enabled_plugins.append(HERMES_PLUGIN_NAME)
    plugins["enabled"] = enabled_plugins

    if enabled and "disabled" in plugins:
        disabled_plugins = plugins["disabled"]
        if not isinstance(disabled_plugins, list):
            raise HookConfigError("Hermes plugins.disabled must be an array")
        plugins["disabled"] = [item for item in disabled_plugins if item != HERMES_PLUGIN_NAME]


def _remove_legacy_hermes_shell_hooks(config: dict[str, Any], spec: HookAgentSpec) -> None:
    """Remove command hooks written by older MemOS releases to avoid duplicates."""
    for event in spec.events:
        _remove_event(config, spec, event)


def _install_hermes_plugin(spec: HookAgentSpec) -> Path:
    """Install the Hermes Python plugin used by CLI, gateway, TUI, and Desktop."""
    plugin_dir = spec.config_path()
    if plugin_dir.exists() and not plugin_dir.is_dir():
        raise HookConfigError(f"Hermes plugin path is not a directory: {plugin_dir}")
    if plugin_dir.exists() and any(plugin_dir.iterdir()) and not _hermes_plugin_is_managed(plugin_dir):
        raise HookConfigError(f"Refusing to overwrite a user-owned Hermes plugin: {plugin_dir}")

    config_path = _hermes_config_path(spec)
    config = _read_yaml_config(config_path)
    _remove_legacy_hermes_shell_hooks(config, spec)
    _set_hermes_plugin_enabled(config, enabled=True)

    argv = _resolve_command_argv(spec.agent)
    plugin_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(plugin_dir / "plugin.yaml", hermes_plugin_manifest())
    _atomic_write_text(plugin_dir / "__init__.py", hermes_plugin_entry(argv, spec))
    _atomic_write_yaml(config_path, config)
    return plugin_dir


def _uninstall_hermes_plugin(spec: HookAgentSpec) -> bool:
    """Remove only the managed Hermes plugin plus legacy managed shell hooks."""
    plugin_dir = spec.config_path()
    user_owned_plugin = plugin_dir.exists() and not _hermes_plugin_is_managed(plugin_dir)
    removed = False
    if plugin_dir.is_dir() and not user_owned_plugin:
        shutil.rmtree(plugin_dir)
        removed = True

    config_path = _hermes_config_path(spec)
    if config_path.exists():
        config = _read_yaml_config(config_path)
        _remove_legacy_hermes_shell_hooks(config, spec)
        if not user_owned_plugin:
            _set_hermes_plugin_enabled(config, enabled=False)
        _atomic_write_yaml(config_path, config)
    return removed


def _openclaw_config_path(spec: HookAgentSpec) -> Path:
    configured = os.getenv("OPENCLAW_CONFIG_PATH")
    if configured and configured.strip():
        return Path(configured).expanduser()
    return spec.config_path().parent.parent / "openclaw.json"


def _set_openclaw_plugin_enabled(spec: HookAgentSpec, enabled: bool) -> None:
    """Toggle the managed plugin entry in openclaw.json.

    The plugin lives under the auto-discovered extensions root, so openclaw.json
    only needs registration/enablement (plugins.entries + allowlist), not load paths.
    """
    config_path = _openclaw_config_path(spec)
    config = _read_json_config(config_path)
    if enabled:
        plugins = config.setdefault("plugins", {})
        entries = plugins.setdefault("entries", {})
        entries[ANTIGRAVITY_HOOK_NAME] = {
            "enabled": True,
            "hooks": {
                # Raw conversation access (agent_end) and prompt injection
                # (before_prompt_build prependContext) are permission-gated.
                "allowConversationAccess": True,
                "allowPromptInjection": True,
            },
        }
        allow = plugins.get("allow")
        if isinstance(allow, list) and ANTIGRAVITY_HOOK_NAME not in allow:
            allow.append(ANTIGRAVITY_HOOK_NAME)
    else:
        plugins = config.get("plugins")
        if not isinstance(plugins, dict):
            return
        entries = plugins.get("entries")
        if isinstance(entries, dict):
            entries.pop(ANTIGRAVITY_HOOK_NAME, None)
        allow = plugins.get("allow")
        if isinstance(allow, list) and ANTIGRAVITY_HOOK_NAME in allow:
            plugins["allow"] = [item for item in allow if item != ANTIGRAVITY_HOOK_NAME]
    _atomic_write_json(config_path, config)


def _install_hook_dir(spec: HookAgentSpec) -> Path:
    """Install the OpenClaw plugin directory (manifest + package.json + entry)."""
    plugin_dir = spec.config_path()
    plugin_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(plugin_dir / "openclaw.plugin.json", openclaw_plugin_manifest())
    _atomic_write_text(plugin_dir / "package.json", openclaw_plugin_package_json())
    _atomic_write_text(plugin_dir / "index.js", openclaw_plugin_entry(_resolve_command_argv(spec.agent), spec))
    _set_openclaw_plugin_enabled(spec, True)
    return plugin_dir


def _uninstall_hook_dir(spec: HookAgentSpec) -> bool:
    """Remove the OpenClaw plugin directory when it is MemOS-managed."""
    plugin_dir = spec.config_path()
    entry = plugin_dir / "index.js"
    if not plugin_dir.is_dir() or not entry.is_file():
        return False
    try:
        content = entry.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if MANAGED_MARKER not in content:
        return False
    shutil.rmtree(plugin_dir)
    try:
        _set_openclaw_plugin_enabled(spec, False)
    except HookConfigError:
        pass
    return True


def _install_hook_config(config: dict[str, Any], spec: HookAgentSpec) -> None:
    _install_command_hook_config(config, spec, command_builder=resolve_command)


def _install_command_hook_config(
    config: dict[str, Any],
    spec: HookAgentSpec,
    *,
    command_builder: Any,
) -> None:
    _remove_stale_managed_events(config, spec)
    if spec.config_version is not None and "version" not in config:
        config["version"] = spec.config_version
    phase_events: list[tuple[str, str]] = []
    if spec.search_hook_enabled:
        phase_events.append(("search", spec.search_event))
    phase_events.append(("add", spec.add_event))
    for phase, event in phase_events:
        command = command_builder(spec.agent, event)
        if spec.config_format in {"codex", "claude", "generic_json", "generic_yaml"}:
            hook = _managed_hook(
                command,
                phase,
                include_type=True,
                # Copilot and Antigravity validate command-hook entries
                # against their own schemas; statusMessage is a Codex-style
                # field and can cause the entire entry to be ignored.
                include_status_message=spec.agent not in {"copilot", "antigravity"},
            )
        else:
            hook = _managed_hook(command, phase, include_type=False)

        if spec.agent == "copilot":
            # Copilot CLI/cloud runtimes accept `command` as a fallback, but
            # older CLI builds require the platform-specific `bash` field.
            # Keep both so the same generated file works across versions and
            # on macOS/Linux the exact resolved executable is used.
            hook["bash"] = command
            hook["timeoutSec"] = HOOK_TIMEOUT_SECONDS
            hook.pop("timeout", None)

        if spec.config_layout == "antigravity":
            _append_direct_command_hook(config, spec, event, hook)
        elif spec.config_format in {"codex", "claude"}:
            _append_wrapped_command_hook(config, spec, event, hook)
        else:
            _append_direct_command_hook(config, spec, event, hook)

    if spec.config_format == "cursor":
        config["version"] = config.get("version") or 1


def _git_repository_root() -> Path | None:
    configured = os.getenv("MEMOS_COPILOT_REPO_ROOT")
    if configured and configured.strip():
        return Path(configured).expanduser().resolve()

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=False,
            cwd=Path.cwd(),
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    return Path(root).expanduser().resolve() if root else None


def _copilot_cloud_hook_path() -> Path | None:
    root = _git_repository_root()
    if root is None:
        return None
    return root / ".github" / "hooks" / COPILOT_HOOK_FILENAME


def _install_copilot_hook(spec: HookAgentSpec) -> Path:
    """Install Copilot hooks for both local CLI and repo-level cloud agents."""
    user_path = spec.config_path()
    user_config = _read_config(user_path, spec)
    _install_command_hook_config(user_config, spec, command_builder=resolve_command)
    _write_config(user_path, spec, user_config)

    cloud_path = _copilot_cloud_hook_path()
    if cloud_path is not None:
        cloud_config = _read_config(cloud_path, spec)
        _install_command_hook_config(cloud_config, spec, command_builder=_portable_command)
        _write_config(cloud_path, spec, cloud_config)
    return user_path


def _uninstall_copilot_hook(spec: HookAgentSpec) -> Path | None:
    """Remove Copilot hooks from local CLI config and the current repo cloud config."""
    removed_path: Path | None = None
    for path in (spec.config_path(), _copilot_cloud_hook_path()):
        if path is None or not path.exists():
            continue
        config = _read_config(path, spec)
        for event in spec.events:
            _remove_event(config, spec, event)
        if spec.owns_config_file and "hooks" not in config:
            path.unlink()
        else:
            _write_config(path, spec, config)
        removed_path = removed_path or path
    return removed_path


def install_hook(agent: str = DEFAULT_HOOK_AGENT) -> Path:
    """Install the native hook for one supported agent."""
    spec = get_hook_agent_spec(agent)
    if spec.install_style == "plugin_py":
        return _install_hermes_plugin(spec)
    if spec.install_style == "plugin_js":
        return _install_plugin_js(spec)
    if spec.install_style == "hook_dir":
        return _install_hook_dir(spec)
    if spec.agent == "copilot":
        return _install_copilot_hook(spec)
    path = spec.config_path()
    config = _read_config(path, spec)
    if spec.agent == "antigravity":
        _install_antigravity_adapter(spec)
        _install_command_hook_config(
            config,
            spec,
            command_builder=lambda _agent, event: _antigravity_adapter_command(spec, event),
        )
    else:
        _install_hook_config(config, spec)
    _write_config(path, spec, config)
    return path


def uninstall_hook(agent: str = DEFAULT_HOOK_AGENT) -> Path | None:
    """Remove the native hook for one supported agent."""
    spec = get_hook_agent_spec(agent)
    path = spec.config_path()
    try:
        if spec.install_style == "plugin_py":
            removed = _uninstall_hermes_plugin(spec)
            return path if removed else None
        if spec.install_style == "plugin_js":
            removed = _uninstall_plugin_js(spec)
            return path if removed else None
        if spec.install_style == "hook_dir":
            removed = _uninstall_hook_dir(spec)
            return path if removed else None
        if spec.agent == "copilot":
            return _uninstall_copilot_hook(spec)
        if path.exists():
            config = _read_config(path, spec)
            _remove_stale_managed_events(config, spec)
            for event in spec.events:
                _remove_event(config, spec, event)
            if spec.owns_config_file and "hooks" not in config:
                path.unlink()
            else:
                _write_config(path, spec, config)
        if spec.agent == "antigravity":
            adapter = _antigravity_adapter_path(spec)
            if adapter.is_file() and ANTIGRAVITY_ADAPTER_MARKER in _read_text_file(adapter):
                adapter.unlink()
    finally:
        HookStateStore(agent=spec.agent).clear()
    return path if path.exists() else None
