"""Allow running with ``python -m memos_cli``.

The UTF-8 stdio bootstrap is invoked *before* :mod:`memos_cli.main` is
imported, so Rich :class:`~rich.console.Console` instances constructed at
that module's top level pick up the reconfigured ``sys.stdout`` /
``sys.stderr``.
"""
from memos_cli._encoding import configure_stdio_utf8

# Idempotent — safe to call again from ``memos_cli.main`` for the direct
# ``memos = memos_cli.main:app`` entry-point path.
configure_stdio_utf8()

from memos_cli.main import app  # noqa: E402 — must follow the bootstrap call.

if __name__ == "__main__":
    app()
