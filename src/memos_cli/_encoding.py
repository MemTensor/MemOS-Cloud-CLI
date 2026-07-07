"""Force UTF-8 for stdio and console.

Windows Python defaults ``sys.stdin`` / ``sys.stdout`` / ``sys.stderr`` to the
system ANSI codepage (CP936/GBK on Chinese Windows). When the CLI reads CJK
text from stdin — for example the UTF-8 bytes piped in by Git Bash / MSYS —
Python silently mis-decodes it as GBK. The mis-decoded string is then encoded
to UTF-8 in the outgoing HTTP body, so the API receives double-encoded /
irreversibly corrupted CJK.

``configure_stdio_utf8`` runs at import time (see ``memos_cli/__init__.py``)
so it takes effect before Rich's :class:`~rich.console.Console` — which pins
its encoding from ``sys.stdout`` at construction — is instantiated anywhere
in the package.
"""
from __future__ import annotations

import io
import os
import sys
from typing import Iterable

_STREAM_NAMES: tuple[str, ...] = ("stdin", "stdout", "stderr")


def configure_stdio_utf8(stream_names: Iterable[str] = _STREAM_NAMES) -> None:
    """Reconfigure Python's stdio to UTF-8 and switch the Windows console CP.

    The function is idempotent and safe on non-Windows platforms, on
    already-UTF-8 streams, and on non-standard streams (``pytest``'s capture
    fixture replaces ``sys.stdout`` with a ``StringIO``-like object that has
    neither ``reconfigure`` nor ``buffer``). Every failure is swallowed
    because UTF-8 stdio is a best-effort correctness fix — the caller should
    not crash when it can't be applied (for example inside a sandbox with
    read-only environment).
    """
    # Any Python child process we spawn inherits PYTHONIOENCODING; setting it
    # here makes ``subprocess.run`` invocations behave the same way as the
    # top-level CLI without callers having to remember to pass ``env``.
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    if sys.platform == "win32":
        _switch_windows_console_to_utf8()

    for name in stream_names:
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        if _reconfigure_stream(stream):
            continue
        replacement = _rewrap_stream(stream, line_buffering=(name == "stdout"))
        if replacement is not None:
            setattr(sys, name, replacement)


def _switch_windows_console_to_utf8() -> None:
    """Best-effort switch of the Windows console codepage to CP_UTF8 (65001)."""
    try:
        import ctypes  # local import so non-Windows platforms never touch it

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:
        # Console codepage change is only required for terminal rendering.
        # HTTP request bodies are already correct once the Python-level
        # text wrappers below are reconfigured, so we never propagate this.
        pass


def _reconfigure_stream(stream: object) -> bool:
    """Call ``TextIOWrapper.reconfigure`` when it is available and effective."""
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return False
    try:
        reconfigure(encoding="utf-8", errors="replace")
        return True
    except (OSError, ValueError):
        return False


def _rewrap_stream(stream: object, *, line_buffering: bool) -> io.TextIOWrapper | None:
    """Wrap the raw binary buffer in a fresh UTF-8 :class:`TextIOWrapper`.

    Older Python builds and certain embedded runtimes expose a
    :class:`io.TextIOWrapper`-like object without ``reconfigure``. We fall
    back to wrapping the underlying ``.buffer`` — mirroring what
    ``TextIOWrapper.reconfigure`` does internally — so those environments
    still get UTF-8 stdio.
    """
    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        return None
    try:
        return io.TextIOWrapper(
            buffer,
            encoding="utf-8",
            errors="replace",
            line_buffering=line_buffering,
            write_through=True,
        )
    except (OSError, ValueError):
        return None
