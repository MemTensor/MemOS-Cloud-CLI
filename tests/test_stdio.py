"""Tests for Windows standard-stream compatibility."""
from __future__ import annotations

import unittest

from memos_cli.stdio import _configure_stream


class FakeStream:
    def __init__(self, *, is_terminal: bool) -> None:
        self.is_terminal = is_terminal
        self.calls: list[dict[str, str]] = []

    def isatty(self) -> bool:
        return self.is_terminal

    def reconfigure(self, **options: str) -> None:
        self.calls.append(options)


class StdioCompatibilityTests(unittest.TestCase):
    def test_redirected_stream_uses_utf8(self) -> None:
        stream = FakeStream(is_terminal=False)

        _configure_stream(stream)

        self.assertEqual(
            stream.calls,
            [{"errors": "backslashreplace", "encoding": "utf-8"}],
        )

    def test_terminal_keeps_native_encoding(self) -> None:
        stream = FakeStream(is_terminal=True)

        _configure_stream(stream)

        self.assertEqual(stream.calls, [{"errors": "backslashreplace"}])

    def test_missing_stream_is_ignored(self) -> None:
        _configure_stream(None)


if __name__ == "__main__":
    unittest.main()
