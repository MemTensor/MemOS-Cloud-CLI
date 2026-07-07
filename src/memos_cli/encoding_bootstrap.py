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
byte cannot crash the CLI, and ``errors='surrogateescape'`` on stdin so
unexpected non-UTF-8 input (e.g. a paste from a GBK terminal when ``bin/memos.js``
is bypassed) round-trips as surrogate code points instead of raising
``UnicodeDecodeError`` and crashing the process.  Downstream handlers can still
opt-in to strict decoding at the call site.

All operations are wrapped in narrow ``try/except`` blocks. This bootstrap must
never itself raise; failing to configure UTF-8 must not break the CLI on
platforms where the current behavior is already correct (Linux, macOS, or a
Windows terminal that already uses UTF-8).
"""

from __future__ import annotations

import codecs
import io
import os
import sys
import threading

__all__ = ["ensure_utf8_stdio"]

_APPLIED = False
_LOCK = threading.Lock()

try:
    _UTF8_CANONICAL = codecs.lookup("utf-8").name
except LookupError:  # pragma: no cover — utf-8 is always available in CPython
    _UTF8_CANONICAL = "utf-8"


def _is_utf8_encoding(name: str) -> bool:
    """Return True when ``name`` is any spelling of UTF-8.

    The Python codec registry knows all the aliases (``utf_8``, ``utf-8``,
    ``UTF8``, ``cp65001`` on Windows, ...). ``codecs.lookup`` canonicalizes them
    to the same name, which lets us skip an unnecessary reconfigure when the
    stream is already effectively UTF-8. If the encoding string is unknown we
    conservatively return False so the reconfigure path still runs.
    """

    if not name:
        return False
    try:
        return codecs.lookup(name).name == _UTF8_CANONICAL
    except LookupError:
        return False


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
    if _is_utf8_encoding(current_encoding):
        # Nothing to do — already UTF-8 (handles aliases like ``utf_8``,
        # ``cp65001``, ``UTF-8``, ...).
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
        # NOTE: ``line_buffering=True`` combined with ``write_through=True``
        # raises ``ValueError`` on Python 3.12+ ("can't have line_buffering=True
        # with write_through=True"). ``write_through=True`` already bypasses the
        # Python-level buffer entirely, so ``line_buffering`` adds nothing and
        # is intentionally omitted.
        wrapped = io.TextIOWrapper(
            buffer,
            encoding="utf-8",
            errors=errors,
            write_through=True,
        )
    except (ValueError, OSError):
        return

    # Best-effort flush so any partial output already buffered on the original
    # wrapper (e.g. a prompt written before the bootstrap ran) is not silently
    # discarded when we swap the stream reference.
    try:
        stream.flush()
    except Exception:  # pragma: no cover — flush failure is not fatal
        pass
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
        # 65001 = CP_UTF8.  Read the current code page first and only issue the
        # Set*CP call when it differs — the bootstrap is invoked at import time
        # of ``memos_cli.main``, so a library user doing
        # ``from memos_cli.main import app`` inside a larger Windows application
        # would otherwise have their process-wide console CP flipped as a side
        # effect even when it's already UTF-8.
        if kernel32.GetConsoleOutputCP() != 65001:
            kernel32.SetConsoleOutputCP(65001)
        if kernel32.GetConsoleCP() != 65001:
            kernel32.SetConsoleCP(65001)
    except (AttributeError, OSError):
        return


def ensure_utf8_stdio() -> None:
    """Force ``sys.stdin/stdout/stderr`` to UTF-8 for the current process.

    Idempotent: calling it twice does no additional work. Never raises. The
    check-and-set is guarded by a ``threading.Lock`` so concurrent calls from
    multiple threads still result in exactly one bootstrap; while the CLI
    entry points are effectively single-threaded, the PyInstaller runtime hook
    and library-mode users may exercise this path from unexpected contexts.
    """

    global _APPLIED
    with _LOCK:
        if _APPLIED:
            return

        try:
            _set_env_defaults()
            _reconfigure_stream("stdin", errors="surrogateescape")
            _reconfigure_stream("stdout", errors="replace")
            _reconfigure_stream("stderr", errors="replace")
            _configure_windows_console()
            # Only mark done on full success: if any step raised and we fell
            # into the ``except`` below, streams may be half-configured and a
            # future call should still be free to retry.
            _APPLIED = True
        except Exception:  # pragma: no cover — defensive; bootstrap must not fail
            return
