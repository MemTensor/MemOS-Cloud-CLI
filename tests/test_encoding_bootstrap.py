from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from memos_cli._encoding import configure_stdio_utf8


class _StreamStub:
    """Minimal ``sys.std*`` stand-in with a working ``reconfigure`` hook."""

    def __init__(self, *, encoding: str = "cp936") -> None:
        self.encoding = encoding
        self.errors = "strict"
        self.reconfigure_calls: list[dict] = []

    def reconfigure(self, *, encoding: str, errors: str) -> None:
        self.encoding = encoding
        self.errors = errors
        self.reconfigure_calls.append({"encoding": encoding, "errors": errors})


class _StreamWithoutReconfigure:
    """Older-style stream: no ``reconfigure`` but exposes a raw buffer."""

    def __init__(self) -> None:
        self.encoding = "cp936"
        self.buffer = io.BytesIO()


class ConfigureStdioUtf8Tests(unittest.TestCase):
    def test_reconfigure_is_called_with_utf8_when_available(self) -> None:
        stubs = {name: _StreamStub() for name in ("stdin", "stdout", "stderr")}

        with patch.multiple(
            sys,
            stdin=stubs["stdin"],
            stdout=stubs["stdout"],
            stderr=stubs["stderr"],
        ):
            configure_stdio_utf8()

        # stdin uses surrogateescape (lossless byte round-trip); output
        # streams use replace (display-only, can't destroy user data).
        self.assertEqual(
            stubs["stdin"].reconfigure_calls,
            [{"encoding": "utf-8", "errors": "surrogateescape"}],
        )
        self.assertEqual(stubs["stdin"].encoding, "utf-8")
        for name in ("stdout", "stderr"):
            self.assertEqual(
                stubs[name].reconfigure_calls,
                [{"encoding": "utf-8", "errors": "replace"}],
                msg=f"sys.{name} was not reconfigured to UTF-8/replace",
            )
            self.assertEqual(stubs[name].encoding, "utf-8")

    def test_falls_back_to_rewrap_when_reconfigure_missing(self) -> None:
        raw_stdout = _StreamWithoutReconfigure()

        # Capture ``sys.stdout`` while the patch is still active — reading it
        # after the ``with`` block exits would return the real interpreter's
        # stdout, not the TextIOWrapper installed by ``configure_stdio_utf8``.
        with patch.object(sys, "stdout", raw_stdout):
            with patch.object(sys, "stdin", _StreamStub()):
                with patch.object(sys, "stderr", _StreamStub()):
                    configure_stdio_utf8()
                    replaced = sys.stdout

        self.assertIsInstance(replaced, io.TextIOWrapper)
        self.assertEqual(replaced.encoding.lower(), "utf-8")
        self.assertEqual(replaced.errors, "replace")

    def test_sets_pythonioencoding_when_unset(self) -> None:
        environ = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
        with patch.dict(os.environ, environ, clear=True):
            configure_stdio_utf8(stream_names=())
            self.assertEqual(os.environ.get("PYTHONIOENCODING"), "utf-8")

    def test_preserves_existing_pythonioencoding(self) -> None:
        environ = {**os.environ, "PYTHONIOENCODING": "gbk"}
        with patch.dict(os.environ, environ, clear=True):
            configure_stdio_utf8(stream_names=())
            self.assertEqual(os.environ.get("PYTHONIOENCODING"), "gbk")

    def test_swallows_reconfigure_errors(self) -> None:
        class Angry:
            encoding = "cp936"

            def reconfigure(self, *, encoding: str, errors: str) -> None:
                raise OSError("stream is not seekable")

        angry = Angry()

        with patch.object(sys, "stdin", angry):
            with patch.object(sys, "stdout", _StreamStub()):
                with patch.object(sys, "stderr", _StreamStub()):
                    # Should not raise even though reconfigure() throws.
                    configure_stdio_utf8()

    def test_idempotent_repeated_calls(self) -> None:
        """A second call must be a no-op on an already-UTF-8 stream."""
        stub = _StreamStub()
        with patch.object(sys, "stdin", stub):
            with patch.object(sys, "stdout", _StreamStub()):
                with patch.object(sys, "stderr", _StreamStub()):
                    configure_stdio_utf8()
                    configure_stdio_utf8()

        self.assertEqual(stub.encoding, "utf-8")
        # Second call short-circuits via the ``_is_already_utf8`` guard.
        self.assertEqual(len(stub.reconfigure_calls), 1)

    def test_idempotent_repeated_calls_fallback_path(self) -> None:
        """Second call on the rewrap path must not double-wrap the TextIOWrapper."""
        raw = _StreamWithoutReconfigure()
        with patch.object(sys, "stdout", raw):
            with patch.object(sys, "stdin", _StreamStub()):
                with patch.object(sys, "stderr", _StreamStub()):
                    configure_stdio_utf8()
                    first = sys.stdout
                    configure_stdio_utf8()
                    second = sys.stdout

        # Idempotent: the second call recognised ``first`` was already UTF-8
        # and left it in place instead of wrapping it a second time.
        self.assertIs(first, second)

    def test_missing_streams_are_skipped(self) -> None:
        # Some frozen environments do not attach ``sys.stdin``.
        with patch.object(sys, "stdin", None):
            with patch.object(sys, "stdout", _StreamStub()):
                with patch.object(sys, "stderr", _StreamStub()):
                    # Must not raise AttributeError on the missing stream.
                    configure_stdio_utf8()


class BootstrapImportSideEffectTests(unittest.TestCase):
    def test_importing_package_sets_pythonioencoding(self) -> None:
        """Importing ``memos_cli`` in a fresh interpreter must pin PYTHONIOENCODING.

        Running in the current process is not meaningful: the test framework
        has already imported ``memos_cli`` to discover tests, so a second
        import is a cache hit and never re-executes ``__init__.py``. Spawn a
        subprocess with ``PYTHONIOENCODING`` scrubbed so the bootstrap
        actually runs.
        """
        env = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
        # Ensure the package under test is importable in the subprocess. The
        # repo lays out the package under ``src/`` so we prepend that here.
        repo_src = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"
        )
        env["PYTHONPATH"] = os.pathsep.join(
            [repo_src, env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os, memos_cli; "
                "print(os.environ.get('PYTHONIOENCODING', ''))",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(result.stdout.strip(), "utf-8")


if __name__ == "__main__":
    unittest.main()
