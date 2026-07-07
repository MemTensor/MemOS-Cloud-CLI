"""PyInstaller runtime hook — install UTF-8 stdio inside the frozen binary.

PyInstaller executes files registered via ``runtime_hooks`` before any user
code runs.  Delegating to :func:`memos_cli.encoding_bootstrap.ensure_utf8_stdio`
here means CJK text is safe on Windows even for imports that touch stdio
before ``__main__``/``main`` had a chance to run their own bootstrap call.

If ``memos_cli`` is not importable from this hook (e.g. because the freeze is
unusually staged), we skip silently — the in-package bootstrap will still fire
when the interpreter reaches ``memos_cli/__main__.py``.
"""

from __future__ import annotations

try:
    from memos_cli.encoding_bootstrap import ensure_utf8_stdio

    ensure_utf8_stdio()
except Exception:  # pragma: no cover — hook must never break the launcher
    pass
