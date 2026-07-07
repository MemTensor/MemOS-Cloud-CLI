"""MemOS CLI - Universal memory interface for AI agents.

This package is deliberately side-effect-free at import time: importing
``memos_cli`` for its models/utilities does **not** mutate ``sys.stdout`` /
``sys.stderr`` / ``sys.stdin``. The UTF-8 stdio bootstrap
(:func:`memos_cli._encoding.configure_stdio_utf8`) is invoked from the CLI
entry-points instead — :mod:`memos_cli.__main__` (``python -m memos_cli``)
and the top of :mod:`memos_cli.main` (the ``memos = memos_cli.main:app``
console-script). Keeping ``__init__.py`` inert lets host applications that
consume ``memos_cli`` as a library keep their own stdio configuration.
"""
# Re-exported so entry-points can ``from memos_cli import configure_stdio_utf8``
# without reaching into the private ``_encoding`` module.
from ._encoding import configure_stdio_utf8 as configure_stdio_utf8

__version__ = "1.0.4"
