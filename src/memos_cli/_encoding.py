"""Force UTF-8 for stdio and console.

Windows Python defaults ``sys.stdin`` / ``sys.stdout`` / ``sys.stderr`` to the
system ANSI codepage (CP936/GBK on Chinese Windows). When the CLI reads CJK
text from stdin — for example the UTF-8 bytes piped in by Git Bash / MSYS —
Python silently mis-decodes it as GBK. The mis-decoded string is then encoded
to UTF-8 in the outgoing HTTP body, so the API receives double-encoded /
irreversibly corrupted CJK.

``configure_stdio_utf8`` is called from CLI entry-points (``memos_cli.__main__``
and ``memos_cli.main``) so it takes effect before Rich's
:class:`~rich.console.Console` — which pins its encoding from ``sys.stdout``
at construction — is instantiated anywhere in the package. It is
deliberately *not* invoked from ``memos_cli/__init__.py`` so that library
consumers that only import the package for its models/utilities are not
subject to global stdio mutation.
"""
from __future__ import annotations

import codecs
import io
import os
import sys
import warnings
from typing import Iterable

_STREAM_NAMES: tuple[str, ...] = ("stdin", "stdout", "stderr")
# ``codecs.lookup`` normalises every UTF-8 alias (utf8, utf-8, UTF_8, and any
# platform-specific variant) to a single canonical name, so the idempotency
# guard below stays correct without maintaining a hardcoded alias list.
_UTF8_CANONICAL = codecs.lookup("utf-8").name


def _errors_for(name: str) -> str:
    # stdin uses surrogateescape so undecodable bytes round-trip losslessly
    # into subsequent encode() calls (avoiding silent U+FFFD data loss on
    # ambiguously-encoded input). Output streams use replace because a
    # write-side error can't destroy user data — it only affects display.
    return "surrogateescape" if name == "stdin" else "replace"


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
        errors = _errors_for(name)
        if _is_already_utf8(stream, errors):
            continue
        if _reconfigure_stream(stream, errors=errors):
            continue
        replacement = _rewrap_stream(
            stream, line_buffering=(name == "stdout"), errors=errors
        )
        if replacement is not None:
            setattr(sys, name, replacement)


def _is_already_utf8(stream: object, errors: str) -> bool:
    """True when the stream is already UTF-8 with the desired error handler.

    Guards true idempotency: repeat calls skip reconfigure entirely, and the
    fallback rewrap path never double-wraps an already-wrapped TextIOWrapper.
    Uses :func:`codecs.lookup` so any UTF-8 alias Python may report
    (``utf-8``, ``utf_8``, ``utf8``, ``UTF-8`` …) is recognised uniformly.
    """
    encoding = getattr(stream, "encoding", None)
    if not isinstance(encoding, str):
        return False
    try:
        if codecs.lookup(encoding).name != _UTF8_CANONICAL:
            return False
    except LookupError:
        return False
    existing = getattr(stream, "errors", None)
    return existing == errors


def _switch_windows_console_to_utf8() -> None:
    """Best-effort switch of the Windows console codepage to CP_UTF8 (65001)."""
    # Pre-initialise the return codes so a partial failure (e.g. an exception
    # thrown between the two Win32 calls) cannot leave one variable unbound
    # for the post-try warning check.
    rc_out = 0
    rc_in = 0
    try:
        import ctypes  # local import so non-Windows platforms never touch it

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        rc_out = kernel32.SetConsoleOutputCP(65001)
        rc_in = kernel32.SetConsoleCP(65001)
    except Exception:
        # Console codepage change is only required for terminal rendering.
        # HTTP request bodies are already correct once the Python-level
        # text wrappers below are reconfigured, so we never propagate this.
        return

    # Both Win32 APIs return 0 on failure (e.g. stdout redirected to a pipe
    # in CI). Surface a diagnostic so the failure is observable — the caller
    # can still continue because stream reconfigure below is independent.
    if not rc_out or not rc_in:
        warnings.warn(
            "Failed to switch Windows console codepage to UTF-8; "
            "terminal output may be garbled.",
            RuntimeWarning,
            stacklevel=3,
        )


def _reconfigure_stream(stream: object, *, errors: str) -> bool:
    """Call ``TextIOWrapper.reconfigure`` when it is available and effective."""
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return False
    try:
        reconfigure(encoding="utf-8", errors=errors)
        return True
    except (OSError, ValueError):
        return False


def _rewrap_stream(
    stream: object, *, line_buffering: bool, errors: str
) -> io.TextIOWrapper | None:
    """Wrap the raw binary buffer in a fresh UTF-8 :class:`TextIOWrapper`.

    Older Python builds and certain embedded runtimes expose a
    :class:`io.TextIOWrapper`-like object without ``reconfigure``. We fall
    back to wrapping the underlying ``.buffer`` — mirroring what
    ``TextIOWrapper.reconfigure`` does internally — so those environments
    still get UTF-8 stdio.
    """
    # Flush any buffered writes on the original wrapper before we hand its
    # underlying binary buffer to a fresh TextIOWrapper — otherwise pending
    # bytes still sitting in the old wrapper's write buffer would be lost
    # once the caller starts writing through the replacement wrapper.
    flush = getattr(stream, "flush", None)
    if callable(flush):
        try:
            flush()
        except Exception:
            pass
    buffer = getattr(stream, "buffer", None)
    if buffer is None:
        return None
    try:
        return io.TextIOWrapper(
            buffer,
            encoding="utf-8",
            errors=errors,
            line_buffering=line_buffering,
            write_through=True,
        )
    except (OSError, ValueError):
        return None
