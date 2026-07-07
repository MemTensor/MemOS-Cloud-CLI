"""UTF-8 stdio bootstrap — forces CJK-safe I/O for the frozen Windows binary.

Background
----------
PyInstaller-frozen ``memos.exe`` runs on Windows with ``sys.stdin/stdout/stderr``
bound to the system ANSI code page (CP936/GBK on Simplified Chinese Windows).
When the CLI echoes, prints, or reads CJK text through those streams, characters
round-trip through GBK and are corrupted when the terminal or a downstream pipe
expects UTF-8. HTTP JSON bodies sent by :mod:`requests` are UTF-8 already, but
anything the user sees (or pastes back into another command) can be mangled.

This module ships three defenses that stack cleanly:

1. ``bin/memos.js`` sets ``PYTHONUTF8=1`` and ``PYTHONIOENCODING=utf-8`` in the
   child process environment before ``memos.exe`` starts. That is the only way
   to activate full PEP 540 UTF-8 mode — it must be present before Python
   initializes.
2. This module's :func:`ensure_utf8_stdio` reconfigures ``sys.stdin/stdout/
   stderr`` to UTF-8 at import time. It also nudges ``PYTHONIOENCODING`` and
   ``PYTHONUTF8`` in ``os.environ`` so any child processes we spawn later
   inherit UTF-8 defaults. Called from :mod:`memos_cli.__main__`.
3. A PyInstaller runtime hook (``src/memos_cli/_pyi_rth_utf8.py``) invokes the
   same function at the earliest possible point inside a frozen build, so even
   modules imported during interpreter startup see UTF-8 streams.

The reconfigure uses ``errors='replace'`` on stdout/stderr so a stray non-UTF-8
byte cannot crash the CLI, and ``errors='strict'`` on stdin so bad input is
surfaced rather than silently mangled.

All operations are wrapped in narrow ``try/except`` blocks. This bootstrap must
never itself raise; failing to configure UTF-8 must not break the CLI on
platforms where the current behavior is already correct (Linux, macOS, or a
Windows terminal that already uses UTF-8).
"""

from __future__ import annotations

import io
import os
import sys

__all__ = ["ensure_utf8_stdio"]

_APPLIED = False


def _reconfigure_stream(stream_name: str, *, errors: str) -> None:
    """Reconfigure ``sys.<stream_name>`` to UTF-8 in place when possible.

    ``TextIOWrapper.reconfigure`` was added in Python 3.7 and is the supported
    way to change the encoding of an already-open text stream. If the attribute
    is missing (subclass, mock, or an unusual runtime), or the underlying stream
    is not a text wrapper, we fall back to wrapping the buffer manually.
    """

    stream = getattr(sys, stream_name, None)
    if stream is None:
        return

    current_encoding = getattr(stream, "encoding", "") or ""
    if current_encoding.lower().replace("-", "") == "utf8":
        # Nothing to do — already UTF-8.
        return

    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors=errors)
            return
        except (ValueError, io.UnsupportedOperation, OSError):
            # Fall through to buffer-wrapping fallback.
            pass

    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        return

    try:
        wrapped = io.TextIOWrapper(
            buffer,
            encoding="utf-8",
            errors=errors,
            line_buffering=getattr(stream, "line_buffering", False),
            write_through=True,
        )
    except (ValueError, OSError):
        return

    setattr(sys, stream_name, wrapped)


def _set_env_defaults() -> None:
    """Advertise UTF-8 to child processes without overriding user intent."""

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")


def _configure_windows_console() -> None:
    """Best-effort switch the Windows console code page to UTF-8 (CP 65001).

    Native writes from C extensions (or from anything else bypassing Python's
    text streams) still go through the console code page. Setting the input and
    output CP to 65001 aligns those writes with our UTF-8 streams. Any failure
    is silently ignored — the Python-side reconfigure above is already enough
    for the CLI's own output.
    """

    if sys.platform != "win32":
        return

    try:
        import ctypes  # local import: avoid ctypes cost on non-Windows
    except ImportError:
        return

    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        # 65001 = CP_UTF8.
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except (AttributeError, OSError):
        return


def ensure_utf8_stdio() -> None:
    """Force ``sys.stdin/stdout/stderr`` to UTF-8 for the current process.

    Idempotent: calling it twice does no additional work. Never raises.
    """

    global _APPLIED
    if _APPLIED:
        return

    try:
        _set_env_defaults()
        _reconfigure_stream("stdin", errors="strict")
        _reconfigure_stream("stdout", errors="replace")
        _reconfigure_stream("stderr", errors="replace")
        _configure_windows_console()
    except Exception:  # pragma: no cover — defensive; bootstrap must not fail
        return
    finally:
        _APPLIED = True
