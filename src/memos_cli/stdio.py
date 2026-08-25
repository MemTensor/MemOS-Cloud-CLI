"""Cross-platform standard-stream compatibility helpers."""
from __future__ import annotations

import os
import sys
from typing import Any


def _configure_stream(stream: Any) -> None:
    """Keep Unicode CLI output from crashing on legacy Windows encodings."""
    if stream is None:
        return

    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return

    try:
        is_terminal = bool(stream.isatty())
    except (AttributeError, OSError, ValueError):
        is_terminal = False

    options: dict[str, str] = {"errors": "backslashreplace"}
    if not is_terminal:
        # GitHub Actions and shell pipelines may expose a cp1252 stream even
        # though CLI help contains Unicode. UTF-8 keeps redirected output safe.
        options["encoding"] = "utf-8"

    try:
        reconfigure(**options)
    except (AttributeError, OSError, ValueError):
        # Custom or already-detached streams may not support reconfiguration.
        # Output should remain best-effort instead of breaking CLI startup.
        return


def configure_windows_stdio() -> None:
    """Configure Windows stdout/stderr before Rich or Click creates consoles."""
    if os.name != "nt":
        return

    _configure_stream(sys.stdout)
    _configure_stream(sys.stderr)
