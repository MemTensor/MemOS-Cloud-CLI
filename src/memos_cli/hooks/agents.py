"""Shared native-hook agent registry."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

HookConfigFormat = Literal["codex", "claude", "cursor", "generic_json", "generic_yaml"]
HookResponseStyle = Literal["codex", "cursor", "generic", "copilot", "cline", "antigravity", "hermes", "openclaw"]
HookLayout = Literal["nested", "antigravity"]
HookPhase = Literal["search", "add"]
# How the integration lands on disk:
# - "config": the host reads shell-command hooks from a JSON/YAML config file
# - "plugin_js": the host loads a JS plugin file that pipes payloads to the CLI (OpenCode, Cline)
# - "plugin_py": the host loads a Python plugin directory (Hermes CLI/Desktop)
# - "hook_dir": the host discovers hook directories with HOOK.md + handler (OpenClaw)
HookInstallStyle = Literal["config", "plugin_js", "plugin_py", "hook_dir"]
DEFAULT_HOOK_AGENT = "codex"


@dataclass(frozen=True)
class HookAgentSpec:
    """Declarative native-hook contract for one host agent."""

    agent: str
    display_name: str
    search_event: str
    add_event: str
    config_format: HookConfigFormat
    response_style: HookResponseStyle
    search_injection_enabled: bool = True
    search_hook_enabled: bool = True
    config_layout: HookLayout = "nested"
    config_version: int | None = None
    search_aliases: tuple[str, ...] = ()
    add_aliases: tuple[str, ...] = ()
    install_style: HookInstallStyle = "config"
    # When True, the config file is a dedicated MemOS-owned file (safe to delete
    # entirely on uninstall once no managed hooks remain).
    owns_config_file: bool = False
    # When True, only a Stop payload with fullyIdle=true stores the turn;
    # earlier Stop events (background tasks still running) keep the turn state.
    add_requires_fully_idle: bool = False

    @property
    def events(self) -> tuple[str, str]:
        return (self.search_event, self.add_event)

    def event_phase(self, event: str | None) -> HookPhase | None:
        normalized = _normalize_event(event)
        if not normalized:
            return None
        if self.search_hook_enabled and normalized in {
            _normalize_event(self.search_event),
            *map(_normalize_event, self.search_aliases),
        }:
            return "search"
        if normalized in {_normalize_event(self.add_event), *map(_normalize_event, self.add_aliases)}:
            return "add"
        return None

    def event_for_phase(self, phase: HookPhase) -> str:
        return self.search_event if phase == "search" else self.add_event

    def config_path(self) -> Path:
        if self.agent == DEFAULT_HOOK_AGENT:
            return _configured_dir("CODEX_HOME", Path.home() / ".codex") / "hooks.json"
        if self.agent == "cursor":
            return _configured_dir("CURSOR_HOME", Path.home() / ".cursor") / "hooks.json"
        if self.agent == "claude":
            return _configured_dir("CLAUDE_CONFIG_DIR", Path.home() / ".claude") / "settings.json"
        if self.agent == "trae":
            return Path.home() / ".trae" / "hooks.json"
        if self.agent == "trae-cn":
            return Path.home() / ".trae-cn" / "hooks.json"
        if self.agent == "hermes":
            # Python plugins are discovered by both Hermes CLI and Desktop.
            return _configured_dir("HERMES_HOME", Path.home() / ".hermes") / "plugins" / "memos-memory"
        if self.agent == "antigravity":
            return Path.home() / ".gemini" / "config" / "hooks.json"
        if self.agent == "cline":
            # Cline SDK/CLI/Kanban discover the AgentPlugin here. The IDE
            # extensions use separate executable hooks under
            # ~/Documents/Cline/Hooks, which the installer writes alongside it.
            configured = os.getenv("CLINE_DIR") or os.getenv("CLINE_HOME")
            cline_dir = Path(configured).expanduser() if configured and configured.strip() else Path.home() / ".cline"
            return cline_dir / "plugins" / "memos-memory"
        if self.agent == "copilot":
            # Dedicated hook file; Copilot CLI merges ~/.copilot/hooks/*.json at startup.
            # Cloud coding agents only discover repo-level .github/hooks/*.json.
            return _configured_dir("COPILOT_HOME", Path.home() / ".copilot") / "hooks" / "memos-memory.json"
        if self.agent == "openclaw":
            # OpenClaw discovers plugins under the extensions root; enablement lives in openclaw.json.
            state_dir = _configured_dir("OPENCLAW_STATE_DIR", Path.home() / ".openclaw")
            return state_dir / "extensions" / "memos-memory"
        if self.agent == "opencode":
            # OpenCode lifecycle hooks require a JS plugin file, not opencode.json entries.
            configured_dir = os.getenv("OPENCODE_CONFIG_DIR")
            if configured_dir and configured_dir.strip():
                return Path(configured_dir).expanduser() / "plugins" / "memos-memory.js"
            return Path.home() / ".config" / "opencode" / "plugins" / "memos-memory.js"
        if self.agent == "deepseek":
            # dsh loads the generated Cordis plugin from this file via cordis.patch.yml.
            configured = os.getenv("DSH_HOME")
            if configured and configured.strip():
                home = Path(os.path.abspath(Path(configured).expanduser()))
            else:
                home = Path.home() / ".dsh"
            return home / "plugins" / "memos-memory.js"
        raise HookConfigError(f"Unsupported native hook agent: {self.agent}")


class HookConfigError(ValueError):
    """Invalid or unsupported hook configuration."""


HOOK_AGENT_SPECS: dict[str, HookAgentSpec] = {
    DEFAULT_HOOK_AGENT: HookAgentSpec(
        agent=DEFAULT_HOOK_AGENT,
        display_name="Codex",
        search_event="UserPromptSubmit",
        add_event="Stop",
        config_format="codex",
        response_style="codex",
    ),
    "claude": HookAgentSpec(
        agent="claude",
        display_name="Claude Code",
        search_event="UserPromptSubmit",
        add_event="Stop",
        config_format="claude",
        response_style="codex",
    ),
    "trae": HookAgentSpec(
        agent="trae",
        display_name="Trae",
        search_event="UserPromptSubmit",
        add_event="Stop",
        config_format="codex",
        response_style="codex",
        config_version=1,
    ),
    "trae-cn": HookAgentSpec(
        agent="trae-cn",
        display_name="Trae CN",
        search_event="UserPromptSubmit",
        add_event="Stop",
        config_format="codex",
        response_style="codex",
        config_version=1,
    ),
    "cursor": HookAgentSpec(
        agent="cursor",
        display_name="Cursor",
        search_event="beforeSubmitPrompt",
        add_event="afterAgentResponse",
        config_format="cursor",
        response_style="cursor",
        search_injection_enabled=False,
        # Cursor does not support MemOS context injection through this adapter,
        # but beforeSubmitPrompt must still run to capture the user's prompt for
        # the later afterAgentResponse add hook.
        search_hook_enabled=True,
        search_aliases=("UserPromptSubmit",),
        # Cursor's separate stop event can fire alongside afterAgentResponse;
        # it is not an alias for the response-complete event and must never
        # create a second add.
        add_aliases=(),
    ),
    "hermes": HookAgentSpec(
        agent="hermes",
        display_name="Hermes",
        search_event="pre_llm_call",
        add_event="post_llm_call",
        config_format="generic_yaml",
        response_style="hermes",
        install_style="plugin_py",
    ),
    "antigravity": HookAgentSpec(
        agent="antigravity",
        display_name="Antigravity",
        search_event="PreInvocation",
        add_event="Stop",
        config_format="generic_json",
        response_style="antigravity",
        config_layout="antigravity",
        add_requires_fully_idle=True,
    ),
    "cline": HookAgentSpec(
        agent="cline",
        display_name="Cline",
        # IDE extensions execute the UserPromptSubmit/TaskComplete scripts;
        # SDK/CLI/Kanban execute the generated AgentPlugin and pipe those same
        # normalized event names into the shared runner.
        search_event="UserPromptSubmit",
        add_event="TaskComplete",
        config_format="generic_json",
        response_style="cline",
        install_style="plugin_js",
        search_aliases=("before_agent_start", "prompt_submit"),
        add_aliases=("run_end", "agent_end", "TaskCancel", "Stop"),
    ),
    "copilot": HookAgentSpec(
        agent="copilot",
        display_name="Copilot",
        search_event="userPromptTransformed",
        add_event="agentStop",
        config_format="generic_json",
        response_style="copilot",
        config_version=1,
        owns_config_file=True,
        search_aliases=("userPromptSubmitted", "UserPromptSubmit"),
        add_aliases=("Stop",),
    ),
    "opencode": HookAgentSpec(
        agent="opencode",
        display_name="OpenCode",
        # Delivered by the generated plugin file: chat.message -> search, session.idle -> add.
        search_event="chat.message",
        add_event="session.idle",
        config_format="generic_json",
        response_style="generic",
        install_style="plugin_js",
        search_aliases=("context", "UserPromptSubmit"),
        add_aliases=("session_completed", "Stop"),
    ),
    "openclaw": HookAgentSpec(
        agent="openclaw",
        display_name="OpenClaw",
        # Delivered by the generated plugin (api.on typed hooks):
        # before_prompt_build supports prependContext, agent_end observes the final message.
        search_event="before_prompt_build",
        add_event="agent_end",
        config_format="generic_json",
        response_style="openclaw",
        install_style="hook_dir",
        search_aliases=("message:received",),
        add_aliases=("message:sent",),
    ),
    "deepseek": HookAgentSpec(
        agent="deepseek",
        display_name="DeepSeek Harness",
        # Delivered by the generated Cordis plugin registered in ~/.dsh/cordis.patch.yml:
        # agent/pre-step is the interception waterfall, agent/turn-stopping the stop boundary.
        search_event="agent/pre-step",
        add_event="agent/turn-stopping",
        config_format="generic_json",
        response_style="generic",
        install_style="plugin_js",
        search_aliases=("UserPromptSubmit",),
        add_aliases=("Stop",),
    ),
}


def hook_agent_names() -> list[str]:
    """Return supported native-hook agents."""
    return sorted(HOOK_AGENT_SPECS)


def normalize_hook_agent(agent: str) -> str:
    """Normalize and validate a native-hook agent name."""
    normalized = agent.strip().lower().replace("_", "-").replace(" ", "-")
    if normalized in {"claude-code", "claude"}:
        normalized = "claude"
    if normalized in {"opencode-v2", "opencode"}:
        normalized = "opencode"
    if normalized in {"trae-cn", "traecn"}:
        normalized = "trae-cn"
    if normalized in {"github-copilot", "githubcopilot"}:
        normalized = "copilot"
    if normalized not in HOOK_AGENT_SPECS:
        valid = ", ".join(hook_agent_names())
        raise HookConfigError(f"Unsupported native hook agent: {agent}. Valid values: {valid}")
    return normalized


def get_hook_agent_spec(agent: str) -> HookAgentSpec:
    """Return the declarative native-hook spec for an agent."""
    return HOOK_AGENT_SPECS[normalize_hook_agent(agent)]


def is_native_hook_agent(agent: str) -> bool:
    """Return whether an agent has a native hook mapping."""
    try:
        normalize_hook_agent(agent)
    except HookConfigError:
        return False
    return True


def event_phase_for(agent: str, event: str | None) -> HookPhase | None:
    """Resolve a host event into the MemOS memory lifecycle phase."""
    return get_hook_agent_spec(agent).event_phase(event)


def _normalize_event(value: str | None) -> str:
    return (value or "").strip().lower()


def _configured_dir(env_name: str, fallback: Path) -> Path:
    configured = os.getenv(env_name)
    return Path(configured).expanduser() if configured and configured.strip() else fallback
