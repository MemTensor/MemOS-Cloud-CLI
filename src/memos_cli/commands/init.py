"""Initialization command for MemOS CLI."""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Prompt
from typer._completion_shared import install as install_shell_completion

try:
    from typer._completion_shared import _get_shell_name
except ImportError:
    def _get_shell_name() -> str:
        raise RuntimeError("Shell detection is unavailable in this Typer version")

from memos_cli.config import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULT_CONVERSATION_ID,
    DEFAULT_USER_ID,
    load_config,
    MemOSConfig,
    PlatformConfig,
    save_config,
)
from memos_cli.backend.memos_api import APIError, AuthError, get_backend

console = Console()
DEFAULT_BASE_URL = "https://memos.memtensor.cn/api/openmem/v1"
GUIDANCE_START = "<!-- MEMOS_CLI:START -->"
GUIDANCE_END = "<!-- MEMOS_CLI:END -->"

@dataclass(frozen=True)
class AgentConfig:
    """Declarative configuration for a supported agent."""

    skills_dir: Path
    guidance_file: str
    guidance_home: Path | None = None
    guidance_mode: str = "upsert"  # "upsert" | "standalone"


AGENT_REGISTRY: dict[str, AgentConfig] = {
    "codex":       AgentConfig(Path.home() / ".codex" / "skills",                    "AGENTS.md"),
    "cursor":      AgentConfig(Path.home() / ".cursor" / "skills",                   "AGENTS.md"),
    "claude":      AgentConfig(Path.home() / ".claude" / "skills",                   "CLAUDE.md"),
    "openclaw":    AgentConfig(Path.home() / ".openclaw" / "skills",                 "AGENTS.md"),
    "hermes":      AgentConfig(Path.home() / ".hermes" / "skills",                   "SOUL.md"),
    "trae":        AgentConfig(Path.home() / ".trae" / "skills",                     "memos.md",
                               Path.home() / ".trae" / "rules", "standalone"),
    "trae-cn":     AgentConfig(Path.home() / ".trae-cn" / "skills",                  "memos.md",
                               Path.home() / ".trae-cn" / "rules", "standalone"),
    "opencode":    AgentConfig(Path.home() / ".config" / "opencode" / "skills",      "AGENTS.md"),
    "antigravity": AgentConfig(Path.home() / ".gemini" / "antigravity" / "skills",   "GEMINI.md", Path.home() / ".gemini"),
    "workbuddy":   AgentConfig(Path.home() / ".codebuddy" / "skills",                "CODEBUDDY.md"),
    "cline":       AgentConfig(Path.home() / ".cline" / "skills",                    "memos.md", 
                               Path.home() / ".cline" / "rules", "standalone"),
    "copilot":     AgentConfig(Path.home() / ".copilot" / "skills",                  "copilot-instructions.md"),
}

SUPPORTED_SKILL_AGENTS: dict[str, Path] = {
    agent: config.skills_dir for agent, config in AGENT_REGISTRY.items()
}


def _valid_agent_names() -> list[str]:
    """Return all supported agent names, including legacy mapping overrides."""
    return sorted({*AGENT_REGISTRY, *SUPPORTED_SKILL_AGENTS})


def _bundle_root() -> Path:
    """Return the runtime bundle root for source and PyInstaller builds."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[3]


def _detect_completion_shell() -> str | None:
    """Detect the user's current shell for completion installation."""
    shell_env = os.getenv("SHELL")
    if shell_env:
        shell_name = Path(shell_env).name.strip().lower()
        if shell_name in {"zsh", "bash", "fish"}:
            return shell_name
    try:
        shell_name = _get_shell_name()
    except RuntimeError:
        return None
    if shell_name in {"zsh", "bash", "fish"}:
        return shell_name
    return None


def _resolve_skills_dir(agent: str) -> Path:
    """Resolve the global skills installation directory for the target agent."""
    normalized = agent.strip().lower()

    if normalized == "codex":
        codex_home = os.getenv("CODEX_HOME")
        if codex_home:
            return Path(codex_home).expanduser() / "skills"

    cfg = AGENT_REGISTRY.get(normalized)
    target = SUPPORTED_SKILL_AGENTS.get(normalized)
    if target is None and cfg is None:
        valid = ", ".join(_valid_agent_names())
        raise ValueError(f"Unsupported --agent: {agent}. Valid values: {valid}")
    return target if target is not None else cfg.skills_dir


def _install_bundled_skills(agent: str) -> Path:
    """Install bundled MemOS operation skill into the global skills directory."""
    source_dir = _bundle_root() / "skills"
    if not source_dir.exists():
        raise FileNotFoundError(f"Bundled skills directory not found: {source_dir}")

    target_root = _resolve_skills_dir(agent)
    memos_target = target_root / "memos"
    memos_target.mkdir(parents=True, exist_ok=True)

    source_skill = source_dir / "memos-memory"
    if not source_skill.exists():
        raise FileNotFoundError(f"Bundled memory skill directory not found: {source_skill}")

    destination = memos_target / source_skill.name
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source_skill, destination)

    return memos_target


def _remove_bundled_skills(agent: str) -> list[Path]:
    """Remove bundled MemOS operation skill from the global skills directory."""
    target_root = _resolve_skills_dir(agent) / "memos"
    destination = target_root / "memos-memory"
    removed: list[Path] = []

    if destination.exists():
        shutil.rmtree(destination)
        removed.append(destination)

    try:
        target_root.rmdir()
    except OSError:
        pass

    return removed


def _guidance_template_path() -> Path:
    """Return the bundled AGENTS/CLAUDE guidance template path."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "memos_cli" / "templates" / "agent_guidance.md"
    return Path(__file__).resolve().parents[1] / "templates" / "agent_guidance.md"


def _resolve_guidance_file(agent: str) -> Path:
    """Resolve the primary global guidance file path for the target agent."""
    return _resolve_guidance_files(agent)[0]


def _resolve_guidance_files(agent: str) -> list[Path]:
    """Resolve all global guidance file paths for the target agent."""
    normalized = agent.strip().lower()
    if normalized == "openclaw":
        return _resolve_openclaw_guidance_files()

    cfg = AGENT_REGISTRY.get(normalized)
    skills_dir = _resolve_skills_dir(agent)
    guidance_file = cfg.guidance_file if cfg else "AGENTS.md"
    home = cfg.guidance_home if cfg and cfg.guidance_home else skills_dir.parent
    return [home / guidance_file]


def _resolve_openclaw_guidance_files() -> list[Path]:
    """Resolve OpenClaw guidance files across known workspaces."""
    openclaw_home = _resolve_skills_dir("openclaw").parent
    workspace_guidance = openclaw_home / "workspace" / "AGENTS.md"

    # TODO: Read agents.list from ~/.openclaw/openclaw.json and create/update
    # every configured workspace AGENTS.md instead of relying on existing files.
    guidance_files = set(openclaw_home.rglob("AGENTS.md")) if openclaw_home.exists() else set()
    guidance_files.add(workspace_guidance)
    return sorted(guidance_files)


def _resolve_uninstall_guidance_files(agent: str) -> list[Path]:
    """Resolve guidance files to clean during uninstall, including legacy targets."""
    guidance_files = list(_resolve_guidance_files(agent))
    normalized = agent.strip().lower()

    if normalized == "hermes":
        legacy_guidance = _resolve_skills_dir(agent).parent / "AGENTS.md"
        if legacy_guidance not in guidance_files:
            guidance_files.append(legacy_guidance)

    return guidance_files


def _build_agent_guidance(agent: str) -> str:
    """Build agent-specific MemOS CLI guidance content from template."""
    template = _guidance_template_path().read_text(encoding="utf-8")
    plugin_start = template.find("## MemOS Plugin Mode")
    content = template[:plugin_start].rstrip() if plugin_start != -1 else template.rstrip()
    return f"{GUIDANCE_START}\n{content}\n{GUIDANCE_END}\n"


def _build_plugin_agent_guidance(agent: str) -> str:
    """Build agent guidance for environments where the MemOS plugin is installed."""
    template = _guidance_template_path().read_text(encoding="utf-8")
    start = template.find("## MemOS Plugin Mode")
    if start == -1:
        return _build_agent_guidance(agent)
    content = template[start:].rstrip()
    return f"{GUIDANCE_START}\n{content}\n{GUIDANCE_END}\n"


def _upsert_guidance_block(path: Path, content: str) -> None:
    """Insert or replace the managed MemOS CLI guidance block."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if GUIDANCE_START in existing and GUIDANCE_END in existing:
        start = existing.index(GUIDANCE_START)
        end = existing.index(GUIDANCE_END) + len(GUIDANCE_END)
        updated = f"{existing[:start].rstrip()}\n\n{content}\n{existing[end:].lstrip()}"
    else:
        prefix = existing.rstrip()
        updated = f"{prefix}\n\n{content}" if prefix else content
    path.write_text(updated.rstrip() + "\n", encoding="utf-8")


def _remove_guidance_block(path: Path) -> bool:
    """Remove the managed MemOS CLI guidance block from a guidance file."""
    if not path.exists():
        return False

    existing = path.read_text(encoding="utf-8")
    if GUIDANCE_START not in existing or GUIDANCE_END not in existing:
        return False

    start = existing.index(GUIDANCE_START)
    end = existing.index(GUIDANCE_END) + len(GUIDANCE_END)
    updated = f"{existing[:start].rstrip()}\n\n{existing[end:].lstrip()}".strip()

    path.write_text((updated + "\n") if updated else "", encoding="utf-8")
    return True


def _write_standalone_guidance(path: Path, content: str) -> None:
    """Write a standalone guidance file fully managed by MemOS."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


STANDALONE_FRONTMATTER = """\
---
description: MemOS memory management - search and store context for every conversation
alwaysApply: true
---

"""


def _build_standalone_guidance(agent: str, *, memos_plugin: bool = False) -> str:
    """Build standalone guidance with frontmatter (for Trae rules format)."""
    template = _guidance_template_path().read_text(encoding="utf-8")
    if memos_plugin:
        start = template.find("## MemOS Plugin Mode")
        content = template[start:].rstrip() if start != -1 else template.rstrip()
    else:
        plugin_start = template.find("## MemOS Plugin Mode")
        content = template[:plugin_start].rstrip() if plugin_start != -1 else template.rstrip()
    return f"{STANDALONE_FRONTMATTER}{content}\n"


def _remove_standalone_guidance(path: Path) -> bool:
    """Clear a standalone guidance file when it is MemOS-managed."""
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    if not content.startswith(STANDALONE_FRONTMATTER):
        return False
    path.write_text("", encoding="utf-8")
    return True


def _install_agent_guidance(agent: str, *, memos_plugin: bool = False) -> list[Path]:
    """Install or update global MemOS CLI guidance for the target agent."""
    normalized = agent.strip().lower()
    cfg = AGENT_REGISTRY.get(normalized) or AgentConfig(
        _resolve_skills_dir(agent),
        "AGENTS.md",
    )
    guidance_files = _resolve_guidance_files(agent)

    if cfg.guidance_mode == "standalone":
        content = _build_standalone_guidance(agent, memos_plugin=memos_plugin)
        for guidance_file in guidance_files:
            _write_standalone_guidance(guidance_file, content)
    else:
        content = _build_plugin_agent_guidance(agent) if memos_plugin else _build_agent_guidance(agent)
        for guidance_file in guidance_files:
            _upsert_guidance_block(guidance_file, content)
    return guidance_files


def _uninstall_agent_guidance(agent: str) -> list[Path]:
    """Remove MemOS CLI guidance from all known guidance files for the target agent."""
    normalized = agent.strip().lower()
    cfg = AGENT_REGISTRY.get(normalized) or AgentConfig(
        _resolve_skills_dir(agent),
        "AGENTS.md",
    )
    removed: list[Path] = []

    for guidance_file in _resolve_uninstall_guidance_files(agent):
        if cfg.guidance_mode == "standalone":
            changed = _remove_standalone_guidance(guidance_file)
        else:
            changed = _remove_guidance_block(guidance_file)
        if changed:
            removed.append(guidance_file)

    return removed


def _remove_config_file() -> Path | None:
    """Remove the MemOS config file and empty config directory when requested."""
    if not CONFIG_FILE.exists():
        return None
    CONFIG_FILE.unlink()
    try:
        CONFIG_DIR.rmdir()
    except OSError:
        pass
    return CONFIG_FILE




def _install_cli_completion() -> tuple[str, Path] | None:
    """Install shell completion for the current shell when supported."""
    shell = _detect_completion_shell()
    if shell is None:
        return None
    try:
        installed_shell, installed_path = install_shell_completion(
            shell=shell,
            prog_name="memos",
        )
    except Exception:
        return None
    return installed_shell, installed_path


def _has_config_value(value: str | None) -> bool:
    """Return whether a config value is meaningfully set."""
    return bool(value and value.strip())


def _has_complete_init_config(config: MemOSConfig) -> bool:
    """Check whether init can reuse the existing config without prompting."""
    return (
        _has_config_value(config.platform.api_key)
        and _has_config_value(config.defaults.user_id)
        and _has_config_value(config.defaults.conversation_id)
    )


def _masked_api_key(api_key: str) -> str:
    """Mask an API key for prompt hints without exposing the full secret."""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"


def _prompt_existing_config_values(
    config: MemOSConfig,
    api_key: str | None,
    user_id: str | None,
    conversation_id: str | None,
) -> tuple[str, str, str]:
    """Prompt for config values, using existing values when the user presses Enter."""
    console.print(
        "[dim]Press ENTER to keep existing values when shown, "
        "or to use defaults for optional values.[/]\n"
    )

    if not api_key:
        if _has_config_value(config.platform.api_key):
            masked_key = _masked_api_key(config.platform.api_key)
            entered_api_key = Prompt.ask(
                f"[bold]Enter your MemOS API key[/] [dim](current: {masked_key})[/]",
                password=True,
                default="",
                show_default=False,
            )
            api_key = entered_api_key or config.platform.api_key
        else:
            console.print(
                "[dim]Get your API key at:[/] "
                "https://memos-dashboard.openmem.net/cn/apikeys/\n"
            )
            api_key = Prompt.ask(
                "[bold]Enter your MemOS API key[/]",
                password=True,
            )

    if not user_id:
        current_user_id = config.defaults.user_id or DEFAULT_USER_ID
        entered_user_id = Prompt.ask(
            f"Default user ID [dim](current: {current_user_id})[/]",
            default="",
            show_default=False,
        )
        user_id = entered_user_id or current_user_id

    if not conversation_id:
        current_conversation_id = (
            config.defaults.conversation_id or DEFAULT_CONVERSATION_ID
        )
        entered_conversation_id = Prompt.ask(
            f"Default conversation ID [dim](current: {current_conversation_id})[/]",
            default="",
            show_default=False,
        )
        conversation_id = entered_conversation_id or current_conversation_id

    return (
        api_key,
        user_id or DEFAULT_USER_ID,
        conversation_id or DEFAULT_CONVERSATION_ID,
    )


def init_cmd(
    api_key: str | None = typer.Option(None, "--api-key", "-k", help="MemOS API key"),
    user_id: str | None = typer.Option(None, "--user-id", help="Default user ID"),
    conversation_id: str | None = typer.Option(
        None, "--conversation-id", help="Default conversation ID"
    ),
    memos_plugin: bool = typer.Option(
        False,
        "--memos-plugin",
        help="Write plugin-aware guidance when a MemOS memory plugin is installed.",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        help=f"Install skill for target agent: {', '.join(_valid_agent_names())}.",
    ),
):
    """Initialize MemOS CLI and install bundled skills to an explicit agent skills directory."""
    console.print("[bold blue]◆ MemOS CLI Initialization[/]\n")

    if not agent:
        valid = ", ".join(_valid_agent_names())
        console.print(
            f"[red]Error:[/] --agent is required. "
            f"Skill installation target must be specified explicitly ({valid})."
        )
        raise typer.Exit(1)

    try:
        _resolve_skills_dir(agent)
    except ValueError as exc:
        console.print(f"\n[red]Error:[/] {exc}")
        raise typer.Exit(1)

    config_file_exists = CONFIG_FILE.exists()
    existing_config = load_config() if config_file_exists else MemOSConfig()
    has_complete_existing_config = (
        config_file_exists and _has_complete_init_config(existing_config)
    )
    is_interactive = sys.stdin.isatty()

    if config_file_exists:
        console.print(f"[yellow]Existing configuration found at:[/] [dim]{CONFIG_FILE}[/]")

    if is_interactive:
        api_key, user_id, conversation_id = _prompt_existing_config_values(
            existing_config,
            api_key,
            user_id,
            conversation_id,
        )
    elif has_complete_existing_config:
        api_key = api_key or existing_config.platform.api_key
        user_id = user_id or existing_config.defaults.user_id or DEFAULT_USER_ID
        conversation_id = (
            conversation_id
            or existing_config.defaults.conversation_id
            or DEFAULT_CONVERSATION_ID
        )
    else:
        user_id = user_id or existing_config.defaults.user_id or DEFAULT_USER_ID
        conversation_id = (
            conversation_id
            or existing_config.defaults.conversation_id
            or DEFAULT_CONVERSATION_ID
        )

    if not api_key:
        console.print(
            "[red]Error:[/] API key is required. "
            "Pass --api-key, or configure it with "
            "`memos config set platform.api_key <value>` before running init."
        )
        if config_file_exists:
            console.print(f"[dim]Existing config: {CONFIG_FILE}[/]")
        else:
            console.print(
                "[dim]Get your API key at:[/] "
                "https://memos-dashboard.openmem.net/cn/apikeys/"
            )
        raise typer.Exit(1)
    
    # Create and save config
    config = MemOSConfig(
        platform=PlatformConfig(
            api_key=api_key,
            base_url=existing_config.platform.base_url or DEFAULT_BASE_URL,
        ),
    )
    config.defaults.user_id = user_id or DEFAULT_USER_ID
    config.defaults.conversation_id = conversation_id or DEFAULT_CONVERSATION_ID
    config.defaults.framework = agent.strip().lower()

    try:
        get_backend(config).ping()
    except AuthError as exc:
        console.print(f"\n[red]Authentication failed:[/] {exc}")
        raise typer.Exit(1)
    except APIError as exc:
        console.print(f"\n[red]API error:[/] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"\n[red]Error:[/] {exc}")
        raise typer.Exit(1)

    save_config(config)
    try:
        skills_path = _install_bundled_skills(agent)
    except ValueError as exc:
        console.print(f"\n[red]Error:[/] {exc}")
        raise typer.Exit(1)
    guidance_paths = _install_agent_guidance(agent, memos_plugin=memos_plugin)

    console.print("\n[green]✓[/] Configuration saved successfully!")
    console.print(f"  Config file: [dim]~/.memos/config.yaml[/]")
    console.print(f"  Default user ID: [dim]{config.defaults.user_id}[/]")
    console.print(f"  Default conversation ID: [dim]{config.defaults.conversation_id}[/]")
    console.print(f"  Target agent: [dim]{agent}[/]")
    console.print(f"  MemOS plugin: [dim]{'enabled' if memos_plugin else 'disabled'}[/]")
    console.print(f"  Installed skill: [dim]{skills_path / 'memos-memory'}[/]")
    console.print(f"  Agent guidance: [dim]{', '.join(str(path) for path in guidance_paths)}[/]")
    console.print("  Shell completion: [dim]Skipped (disabled during init)[/]")
    if has_complete_existing_config:
        console.print(
            f"  Config variables: [dim]Already available in {CONFIG_FILE}. "
            "Use `memos config set <key> <value>` to update them later.[/]"
        )
    console.print('\n[dim]Try running:[/] memos add "Your first memory"')


def uninstall_cmd(
    agent: str | None = typer.Option(
        None,
        "--agent",
        help=f"Remove MemOS integration for target agent: {', '.join(_valid_agent_names())}.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    remove_config: bool = typer.Option(
        False,
        "--remove-config",
        help="Also remove ~/.memos/config.yaml.",
    ),
):
    """Uninstall MemOS agent integration without removing the npm package itself."""
    console.print("[bold blue]◆ MemOS CLI Uninstall[/]\n")

    if not agent:
        valid = ", ".join(_valid_agent_names())
        console.print(
            f"[red]Error:[/] --agent is required. "
            f"Uninstall target must be specified explicitly ({valid})."
        )
        raise typer.Exit(1)

    try:
        _resolve_skills_dir(agent)
    except ValueError as exc:
        console.print(f"\n[red]Error:[/] {exc}")
        raise typer.Exit(1)

    if not yes:
        confirmed = typer.confirm(
            f"Remove MemOS skills and guidance for agent '{agent}'?"
        )
        if not confirmed:
            console.print("[yellow]Uninstall cancelled.[/]")
            raise typer.Exit()

    removed_skills = _remove_bundled_skills(agent)
    removed_guidance = _uninstall_agent_guidance(agent)
    removed_config = _remove_config_file() if remove_config else None

    console.print("\n[green]✓[/] MemOS agent integration removed.")
    if removed_skills:
        console.print(f"  Removed skill: [dim]{', '.join(str(path) for path in removed_skills)}[/]")
    else:
        console.print("  Removed skill: [dim]Nothing found[/]")

    if removed_guidance:
        console.print(f"  Cleaned guidance: [dim]{', '.join(str(path) for path in removed_guidance)}[/]")
    else:
        console.print("  Cleaned guidance: [dim]Nothing found[/]")

    if remove_config:
        if removed_config:
            console.print(f"  Removed config: [dim]{removed_config}[/]")
        else:
            console.print("  Removed config: [dim]Nothing found[/]")

    console.print(
        "\n[dim]To remove the global CLI binary, run:[/] "
        "npm uninstall -g @memtensor/memos-cloud-cli"
    )
