"""Tests for :mod:`memos_cli.encoding_bootstrap`.

The bootstrap runs at import time on every Windows install, so it must be:

* idempotent — calling it repeatedly is a no-op;
* safe on non-Windows platforms — it must not corrupt stdio that is already
  UTF-8;
* resilient — a broken TextIOWrapper or a mock stream must not raise;
* pushing UTF-8 defaults into ``os.environ`` for child processes.

These tests exercise :func:`ensure_utf8_stdio` against fabricated stdio streams
so they run consistently in CI regardless of the host platform's real
``sys.stdout.encoding``.
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from unittest.mock import patch


class EnsureUtf8StdioTests(unittest.TestCase):
    def setUp(self) -> None:
        # Reset the module-level cache so each test gets a fresh apply cycle.
        import memos_cli.encoding_bootstrap as bootstrap

        self.bootstrap = bootstrap
        bootstrap._APPLIED = False

        self._saved_stdin = sys.stdin
        self._saved_stdout = sys.stdout
        self._saved_stderr = sys.stderr
        self._saved_env = {
            "PYTHONIOENCODING": os.environ.get("PYTHONIOENCODING"),
            "PYTHONUTF8": os.environ.get("PYTHONUTF8"),
        }
        os.environ.pop("PYTHONIOENCODING", None)
        os.environ.pop("PYTHONUTF8", None)

    def tearDown(self) -> None:
        sys.stdin = self._saved_stdin
        sys.stdout = self._saved_stdout
        sys.stderr = self._saved_stderr
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.bootstrap._APPLIED = False

    # ------------------------------------------------------------------ utils

    def _make_stream(self, encoding: str) -> io.TextIOWrapper:
        buffer = io.BufferedWriter(io.BytesIO())
        return io.TextIOWrapper(buffer, encoding=encoding, errors="strict")

    def _make_input_stream(self, payload: bytes, encoding: str) -> io.TextIOWrapper:
        buffer = io.BufferedReader(io.BytesIO(payload))
        return io.TextIOWrapper(buffer, encoding=encoding, errors="strict")

    # ------------------------------------------------------------------ cases

    def test_reconfigures_gbk_stdout_to_utf8(self) -> None:
        gbk_stdout = self._make_stream("gbk")
        sys.stdout = gbk_stdout

        self.bootstrap.ensure_utf8_stdio()

        # After the bootstrap, sys.stdout speaks UTF-8 so CJK text writes cleanly.
        self.assertEqual(sys.stdout.encoding.lower().replace("-", ""), "utf8")
        sys.stdout.write("测试中文记忆存储")
        sys.stdout.flush()

    def test_reconfigures_gbk_stderr_to_utf8_with_replace_errors(self) -> None:
        gbk_stderr = self._make_stream("gbk")
        sys.stderr = gbk_stderr

        self.bootstrap.ensure_utf8_stdio()

        self.assertEqual(sys.stderr.encoding.lower().replace("-", ""), "utf8")
        # ``errors='replace'`` on stderr means a stray non-UTF-8 payload cannot
        # explode the CLI mid-error-message.
        self.assertEqual(sys.stderr.errors, "replace")

    def test_reconfigures_gbk_stdin_to_utf8(self) -> None:
        payload = "测试中文记忆存储\n".encode("utf-8")
        sys.stdin = self._make_input_stream(payload, "gbk")

        self.bootstrap.ensure_utf8_stdio()

        self.assertEqual(sys.stdin.encoding.lower().replace("-", ""), "utf8")
        # Contract per the module docstring: stdin uses
        # ``errors='surrogateescape'`` so unexpected non-UTF-8 bytes (e.g. a
        # paste from a CP936 terminal when ``bin/memos.js`` is bypassed) do
        # NOT raise ``UnicodeDecodeError`` and crash the CLI.  See OCR round-2
        # Finding 3.
        self.assertEqual(sys.stdin.errors, "surrogateescape")
        self.assertEqual(sys.stdin.readline().rstrip("\n"), "测试中文记忆存储")

    def test_stdin_survives_non_utf8_bytes_via_surrogateescape(self) -> None:
        # A stray GBK byte (0x80..0xFF that is not valid UTF-8) must not raise
        # UnicodeDecodeError — it should round-trip as a surrogate code point.
        # This is the exact scenario OCR round-2 Finding 3 flagged as a
        # regression risk when ``errors='strict'`` was the default.
        payload = b"hello \xff world\n"
        sys.stdin = self._make_input_stream(payload, "gbk")

        self.bootstrap.ensure_utf8_stdio()

        # Must not raise.
        line = sys.stdin.readline()
        self.assertTrue(line.startswith("hello "))
        self.assertTrue(line.endswith(" world\n"))

    def test_leaves_utf8_streams_untouched(self) -> None:
        utf8_stdout = self._make_stream("utf-8")
        sys.stdout = utf8_stdout

        self.bootstrap.ensure_utf8_stdio()

        self.assertIs(sys.stdout, utf8_stdout)

    def test_treats_utf_8_alias_as_already_utf8(self) -> None:
        # Python's codec registry canonicalizes ``utf_8`` and ``UTF-8`` to the
        # same codec as ``utf-8``.  The bootstrap must recognise those spellings
        # so it does not needlessly re-wrap a stream that is already effectively
        # UTF-8.
        for alias in ("utf_8", "UTF-8"):
            with self.subTest(alias=alias):
                self.bootstrap._APPLIED = False
                stream = self._make_stream(alias)
                sys.stdout = stream
                self.bootstrap.ensure_utf8_stdio()
                self.assertIs(sys.stdout, stream)

        # ``cp65001`` is a Windows-only codec alias; on POSIX systems Python's
        # codec registry does not know about it and ``io.TextIOWrapper(...,
        # encoding='cp65001')`` inside ``_make_stream`` raises ``LookupError``.
        # Only exercise this subtest where the alias is actually registered so
        # POSIX CI does not error out on stream construction.
        try:
            import codecs

            codecs.lookup("cp65001")
        except LookupError:
            pass
        else:
            with self.subTest(alias="cp65001"):
                self.bootstrap._APPLIED = False
                stream = self._make_stream("cp65001")
                sys.stdout = stream
                self.bootstrap.ensure_utf8_stdio()
                self.assertIs(sys.stdout, stream)

    def test_sets_env_defaults_for_child_processes(self) -> None:
        self.bootstrap.ensure_utf8_stdio()

        self.assertEqual(os.environ.get("PYTHONUTF8"), "1")
        self.assertEqual(os.environ.get("PYTHONIOENCODING"), "utf-8")

    def test_does_not_override_user_env_choices(self) -> None:
        # Scope note: this test only guards ``_set_env_defaults`` — it does not
        # (and should not) assert anything about whether ``sys.stdout``/
        # ``sys.stderr`` were reconfigured. The stream reconfigure path is
        # independent of the env-var path and is covered by the dedicated
        # ``test_reconfigures_*`` and ``test_leaves_utf8_streams_untouched``
        # tests.  Here we pin the invariant "user's PYTHONUTF8/PYTHONIOENCODING
        # override is preserved" so a future refactor cannot silently start
        # clobbering it.
        os.environ["PYTHONUTF8"] = "0"
        os.environ["PYTHONIOENCODING"] = "latin-1"

        # Also install a UTF-8 stream so no reconfigure happens as a side
        # effect — makes it explicit that we are testing env vars only.
        sys.stdout = self._make_stream("utf-8")
        sys.stderr = self._make_stream("utf-8")

        self.bootstrap.ensure_utf8_stdio()

        self.assertEqual(os.environ["PYTHONUTF8"], "0")
        self.assertEqual(os.environ["PYTHONIOENCODING"], "latin-1")

    def test_is_idempotent(self) -> None:
        gbk_stdout = self._make_stream("gbk")
        sys.stdout = gbk_stdout

        self.bootstrap.ensure_utf8_stdio()
        first = sys.stdout

        self.bootstrap.ensure_utf8_stdio()
        second = sys.stdout

        # Second call must be a no-op — the stream stays the same wrapper.
        self.assertIs(first, second)

    def test_mid_sequence_failure_does_not_latch_applied_flag(self) -> None:
        # If the bootstrap crashes partway through (e.g. reconfiguring stdin
        # blows up before stdout/stderr are touched), the idempotency flag must
        # NOT be set — a later retry should be free to complete the work.
        original_reconfigure = self.bootstrap._reconfigure_stream

        call_count = {"n": 0}

        def flaky(stream_name: str, *, errors: str) -> None:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("boom on first attempt")
            original_reconfigure(stream_name, errors=errors)

        with patch.object(self.bootstrap, "_reconfigure_stream", flaky):
            # First call should swallow the exception and leave _APPLIED False.
            self.bootstrap.ensure_utf8_stdio()
            self.assertFalse(
                self.bootstrap._APPLIED,
                "flag must not latch when bootstrap fails mid-sequence",
            )

        # Second call runs cleanly and finishes the work.
        gbk_stdout = self._make_stream("gbk")
        sys.stdout = gbk_stdout
        self.bootstrap.ensure_utf8_stdio()
        self.assertTrue(self.bootstrap._APPLIED)
        self.assertEqual(sys.stdout.encoding.lower().replace("-", ""), "utf8")

    def test_reconfigure_failure_falls_back_to_buffer_wrap(self) -> None:
        class FakeStream:
            def __init__(self, buffer: io.BufferedWriter) -> None:
                self.encoding = "gbk"
                self.errors = "strict"
                self.line_buffering = False
                self.buffer = buffer

            def reconfigure(self, **_: object) -> None:
                raise io.UnsupportedOperation("cannot reconfigure")

        underlying = io.BufferedWriter(io.BytesIO())
        sys.stdout = FakeStream(underlying)

        self.bootstrap.ensure_utf8_stdio()

        # Fallback path swaps sys.stdout for a fresh TextIOWrapper on the same
        # buffer.  It must be UTF-8 and writable.
        self.assertIsInstance(sys.stdout, io.TextIOWrapper)
        self.assertEqual(sys.stdout.encoding.lower().replace("-", ""), "utf8")
        # Contract per the module docstring and ``_reconfigure_stream`` call
        # site: stdout uses ``errors='replace'`` so a stray non-UTF-8 byte
        # cannot crash the CLI mid-write. Pin the value so a regression that
        # hardcodes ``errors='strict'`` on the fallback path is caught here.
        self.assertEqual(sys.stdout.errors, "replace")
        sys.stdout.write("测试")
        sys.stdout.flush()

    def test_missing_buffer_and_reconfigure_is_survivable(self) -> None:
        class BrokenStream:
            encoding = "gbk"

        sys.stdout = BrokenStream()

        # Must not raise even though we cannot fix this stream.
        self.bootstrap.ensure_utf8_stdio()

        # Still the broken stream — we swallowed the failure by design.
        self.assertIsInstance(sys.stdout, BrokenStream)

    def test_windows_console_cp_set_when_on_win32(self) -> None:
        calls: list[int] = []

        class FakeKernel32:
            # Report a non-UTF-8 code page so the bootstrap decides both
            # SetConsole*CP calls are necessary. 936 = CP936/GBK, the exact
            # scenario the bootstrap targets.
            def GetConsoleOutputCP(self) -> int:
                return 936

            def GetConsoleCP(self) -> int:
                return 936

            def SetConsoleOutputCP(self, cp: int) -> None:
                calls.append(cp)

            def SetConsoleCP(self, cp: int) -> None:
                calls.append(cp)

        class FakeWindll:
            kernel32 = FakeKernel32()

        fake_ctypes = type(sys)("ctypes")  # a fresh module-like object
        fake_ctypes.windll = FakeWindll()

        with patch.object(sys, "platform", "win32"), patch.dict(
            sys.modules, {"ctypes": fake_ctypes}
        ):
            self.bootstrap.ensure_utf8_stdio()

        # Order of the two SetConsole*CP calls is an implementation detail —
        # what matters is that both code pages were switched to UTF-8 (65001).
        # ``assertCountEqual`` asserts the multiset without pinning ordering.
        self.assertCountEqual(calls, [65001, 65001])

    def test_windows_console_cp_skipped_when_already_utf8(self) -> None:
        # If the current console code page is already 65001 (CP_UTF8) the
        # bootstrap must NOT re-issue SetConsole*CP. This keeps side effects
        # off Windows library users whose host application already runs in
        # UTF-8 mode (see OCR round-2 Finding 4).
        set_calls: list[int] = []

        class FakeKernel32:
            def GetConsoleOutputCP(self) -> int:
                return 65001

            def GetConsoleCP(self) -> int:
                return 65001

            def SetConsoleOutputCP(self, cp: int) -> None:
                set_calls.append(cp)

            def SetConsoleCP(self, cp: int) -> None:
                set_calls.append(cp)

        class FakeWindll:
            kernel32 = FakeKernel32()

        fake_ctypes = type(sys)("ctypes")
        fake_ctypes.windll = FakeWindll()

        with patch.object(sys, "platform", "win32"), patch.dict(
            sys.modules, {"ctypes": fake_ctypes}
        ):
            self.bootstrap.ensure_utf8_stdio()

        self.assertEqual(set_calls, [])

    @unittest.skipIf(
        sys.platform == "win32",
        "POSIX-only: on Windows this test would falsely pass because the real "
        "ctypes.windll dance actually executes; the Windows path is covered by "
        "test_windows_console_cp_set_when_on_win32 via patching.",
    )
    def test_does_not_call_windows_console_cp_on_posix(self) -> None:
        # On non-Windows platforms the ctypes.windll dance is skipped.  If it
        # ran and reached ctypes.windll on Linux, importing would fail.  So the
        # bare fact that this call succeeds proves the guard works.
        self.bootstrap.ensure_utf8_stdio()


if __name__ == "__main__":
    unittest.main()
