"""Initialization command for MemOS CLI."""
from __future__ import annotations

import os
import shutil
import sys
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
    DEFAULT_CONVERSATION_ID,
    DEFAULT_USER_ID,
    MemOSConfig,
    PlatformConfig,
    save_config,
)
from memos_cli.backend.memos_api import APIError, AuthError, get_backend

console = Console()
DEFAULT_BASE_URL = "https://memos.memtensor.cn/api/openmem/v1"
GUIDANCE_START = "<!-- MEMOS_CLI:START -->"
GUIDANCE_END = "<!-- MEMOS_CLI:END -->"
SUPPORTED_SKILL_AGENTS = {
    "codex": Path.home() / ".codex" / "skills",
    "cursor": Path.home() / ".cursor" / "skills",
    "claude": Path.home() / ".claude" / "skills",
    "openclaw": Path.home() / ".openclaw" / "skills",
    "hermes": Path.home() / ".hermes" / "skills",
}


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

    target = SUPPORTED_SKILL_AGENTS.get(normalized)
    if target is None:
        valid = ", ".join(sorted(SUPPORTED_SKILL_AGENTS))
        raise ValueError(f"Unsupported --agent: {agent}. Valid values: {valid}")
    return target


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

    skills_root = _resolve_skills_dir(agent)
    agent_home = skills_root.parent
    if normalized == "claude":
        return [agent_home / "CLAUDE.md"]
    return [agent_home / "AGENTS.md"]


def _resolve_openclaw_guidance_files() -> list[Path]:
    """Resolve OpenClaw guidance files across known workspaces."""
    openclaw_home = _resolve_skills_dir("openclaw").parent
    workspace_guidance = openclaw_home / "workspace" / "AGENTS.md"

    # TODO: Read agents.list from ~/.openclaw/openclaw.json and create/update
    # every configured workspace AGENTS.md instead of relying on existing files.
    guidance_files = set(openclaw_home.rglob("AGENTS.md")) if openclaw_home.exists() else set()
    guidance_files.add(workspace_guidance)
    return sorted(guidance_files)


def _build_agent_guidance(agent: str) -> str:
    """Build agent-specific MemOS CLI guidance content from template."""
    template = _guidance_template_path().read_text(encoding="utf-8")
    content = template.rstrip()
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


def _install_agent_guidance(agent: str, *, memos_plugin: bool = False) -> list[Path]:
    """Install or update global MemOS CLI guidance for the target agent."""
    guidance_files = _resolve_guidance_files(agent)
    guidance_content = _build_plugin_agent_guidance(agent) if memos_plugin else _build_agent_guidance(agent)
    for guidance_file in guidance_files:
        _upsert_guidance_block(guidance_file, guidance_content)
    return guidance_files


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
        help="Install skill for target agent: codex, cursor, claude, openclaw, or hermes.",
    ),
):
    """Initialize MemOS CLI and install bundled skills to an explicit agent skills directory."""
    console.print("[bold blue]◆ MemOS CLI Initialization[/]\n")

    if not agent:
        console.print(
            "[red]Error:[/] --agent is required. "
            "Skill installation target must be specified explicitly "
            "(codex, cursor, claude, openclaw, or hermes)."
        )
        raise typer.Exit(1)

    try:
        _resolve_skills_dir(agent)
    except ValueError as exc:
        console.print(f"\n[red]Error:[/] {exc}")
        raise typer.Exit(1)

    # Get API key
    if not api_key:
        api_key = Prompt.ask(
            "[bold]Enter your MemOS API key[/]",
            password=True,
        )

    if not api_key:
        console.print("[red]Error:[/] API key is required")
        raise typer.Exit(1)

    if not user_id:
        user_id = Prompt.ask(
            "Default user ID",
            default=DEFAULT_USER_ID,
        )

    if not conversation_id:
        conversation_id = Prompt.ask(
            "Default conversation ID",
            default=DEFAULT_CONVERSATION_ID,
        )
    
    # Create and save config
    config = MemOSConfig(
        platform=PlatformConfig(
            api_key=api_key,
            base_url=DEFAULT_BASE_URL,
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
    console.print('\n[dim]Try running:[/] memos add "Your first memory"')
