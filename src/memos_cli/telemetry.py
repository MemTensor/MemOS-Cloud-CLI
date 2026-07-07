"""Telemetry reporting for MemOS CLI."""
from __future__ import annotations

import os
import json
import subprocess
from typing import Any

from memos_cli.config import load_config
from memos_cli.state import get_runtime_options


def build_source_identifier(framework: str | None = None) -> str:
    """Build the source identifier used in telemetry and request headers."""
    normalized = framework.strip().lower() if framework else None
    return f"cli-{normalized}" if normalized else "cli"


def capture_event(event_name: str, properties: dict[str, Any] | None = None) -> None:
    """Capture telemetry event (non-blocking, never fails)."""
    try:
        if properties is None:
            properties = {}

        framework = detect_framework()
        properties["source"] = build_source_identifier(framework)
        if framework:
            properties["framework"] = framework

        _log_event(event_name, properties)
    except Exception:
        pass


def detect_framework() -> str | None:
    """Detect which agent framework is calling the CLI."""
    runtime_framework = get_runtime_options().framework
    if runtime_framework:
        return runtime_framework.strip().lower()

    config_framework = load_config().defaults.framework
    if config_framework:
        return config_framework.strip().lower()

    if framework := os.getenv("MEMOS_FRAMEWORK"):
        return framework.strip().lower()

    if os.getenv("CODEX_HOME") or os.getenv("CODEX_SANDBOX"):
        return "codex"
    if os.getenv("CURSOR_TRACE_ID") or os.getenv("CURSOR_AGENT"):
        return "cursor"
    if os.getenv("CLAUDECODE") or os.getenv("CLAUDE_CODE_ENTRYPOINT"):
        return "claude"
    if os.getenv("OPENCLAW_CONFIG"):
        return "openclaw"
    if os.getenv("HERMES_AGENT"):
        return "hermes"

    try:
        result = subprocess.run(
            ["ps", "-o", "command=", "-p", str(os.getppid())],
            check=False,
            capture_output=True,
            text=True,
        )
        cmdline = result.stdout.strip().lower()
        if "codex" in cmdline:
            return "codex"
        if "cursor" in cmdline:
            return "cursor"
        if "claude" in cmdline:
            return "claude"
        if "openclaw" in cmdline:
            return "openclaw"
        if "hermes" in cmdline:
            return "hermes"
    except Exception:
        pass

    return None


def _log_event(event_name: str, properties: dict) -> None:
    """Log event to local file for attribution and debugging."""
    try:
        from pathlib import Path
        log_dir = Path.home() / ".memos" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / "telemetry.log"
        event_data = {
            "event": event_name,
            "properties": properties,
        }
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_data, ensure_ascii=False) + "\n")
    except Exception:
        pass
