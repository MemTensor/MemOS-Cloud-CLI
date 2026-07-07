"""Regression tests for the npm launcher and PyInstaller onedir spec.

These guard the fix for issue #10: PyInstaller onefile packaging fails in
sandboxed environments (Codex Desktop, hardened seccomp profiles, IPC-less
containers) because the onefile bootloader tries to allocate a SysV IPC
semaphore via `semctl` and the sandbox denies the syscall.

Two surfaces we defend:

- ``bin/memos.js`` — must prefer the onedir layout at ``bin/memos/{exe}``,
  fall back to the legacy single-file path at ``bin/{exe}`` for users on
  cached pre-fix installs, and print a helpful error if neither is present.
  Exit codes from the child process must propagate through the launcher.
- ``memos.spec`` — must remain in onedir mode: ``COLLECT(`` present,
  ``exclude_binaries=True`` set on the ``EXE`` call, and no
  ``runtime_tmpdir=`` argument (which is onefile-only). Trip these if
  someone accidentally reverts to onefile.
"""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_PATH = REPO_ROOT / "bin" / "memos.js"
SPEC_PATH = REPO_ROOT / "memos.spec"


def _node_available() -> bool:
    return shutil.which("node") is not None


@unittest.skipIf(sys.platform == "win32", "Fake bash binaries cannot run on Windows")
@unittest.skipUnless(_node_available(), "node is not available on PATH")
class NpmLauncherResolutionTests(unittest.TestCase):
    """Drive the real bin/memos.js under node against a fake package root."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        # Register cleanup immediately so a later setUp failure (e.g. the
        # shutil.copy below) can't leak the temp dir.
        self.addCleanup(self.tmp.cleanup)
        self.pkg_root = Path(self.tmp.name)
        self.bin_dir = self.pkg_root / "bin"
        self.bin_dir.mkdir(parents=True)
        # Pin CommonJS module resolution locally. Without a package.json
        # at (or above) the launcher, node can walk up the directory tree
        # and pick up an ambient package.json whose "type": "module"
        # setting turns .js files into ES modules — the real launcher
        # uses CommonJS require() so we mirror that here.
        (self.pkg_root / "package.json").write_text('{"type": "commonjs"}\n')
        # Copy the real launcher into the fake package layout — the
        # launcher resolves paths relative to __dirname, so we need it in
        # <pkg>/bin/memos.js to exercise the resolution logic honestly.
        shutil.copy(LAUNCHER_PATH, self.bin_dir / "memos.js")

    def _write_fake_binary(self, target: Path, exit_code: int = 0, echo: str = "") -> None:
        """Write a shell script that pretends to be the memos executable."""
        target.parent.mkdir(parents=True, exist_ok=True)
        script = "#!/usr/bin/env bash\n"
        if echo:
            # shlex.quote guards against callers passing a string with
            # embedded quotes/metacharacters that would otherwise break
            # the generated shell script.
            script += f"echo {shlex.quote(echo)}\n"
        script += f"exit {exit_code}\n"
        target.write_text(script)
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def _invoke_launcher(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["node", str(self.bin_dir / "memos.js")],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_resolves_onedir_binary_when_present(self) -> None:
        onedir_exe = self.bin_dir / "memos" / "memos"
        self._write_fake_binary(onedir_exe, exit_code=0, echo="ONEDIR-OK")
        # Note: we cannot also drop a "real" legacy binary at
        # ``bin/memos`` to exercise the priority branch — the onedir
        # layout requires ``bin/memos`` to be a *directory* (holding the
        # ``memos`` executable), and the legacy layout requires it to be
        # a *file*. The two paths are the same and mutually exclusive on
        # any real filesystem, so priority is enforced structurally by
        # the launcher's ``if existsSync(onedir) else if existsSync(legacy)``
        # ordering rather than by physical cohabitation.
        result = self._invoke_launcher()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("ONEDIR-OK", result.stdout)

    def test_falls_back_to_legacy_single_file(self) -> None:
        # Only the legacy single-file binary is present. Simulates a user
        # who upgraded from a pre-fix cached install where postinstall
        # never had the chance to switch layouts.
        legacy_exe = self.bin_dir / "memos"
        self._write_fake_binary(legacy_exe, exit_code=0, echo="LEGACY-OK")
        result = self._invoke_launcher()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("LEGACY-OK", result.stdout)

    def test_missing_binary_reports_reinstall(self) -> None:
        # Neither layout present — expect a friendly reinstall hint and
        # a non-zero exit code so downstream shells see the failure.
        result = self._invoke_launcher()
        self.assertEqual(result.returncode, 1)
        self.assertIn("MemOS CLI binary is not installed", result.stderr)
        self.assertIn("Reinstall", result.stderr)

    def test_propagates_child_exit_code(self) -> None:
        onedir_exe = self.bin_dir / "memos" / "memos"
        self._write_fake_binary(onedir_exe, exit_code=42)
        result = self._invoke_launcher()
        self.assertEqual(result.returncode, 42)


class SpecFileIsOnedirTests(unittest.TestCase):
    """Cheap textual guards to catch accidental onefile regressions."""

    @classmethod
    def setUpClass(cls) -> None:
        # A clean skip beats an opaque FileNotFoundError when running the
        # test suite in an environment that lacks the spec file (e.g. a
        # partial checkout or a rename in progress).
        if not SPEC_PATH.exists():
            raise unittest.SkipTest(f"memos.spec not found at {SPEC_PATH}")
        cls.spec_text = SPEC_PATH.read_text()

    def test_spec_uses_collect(self) -> None:
        self.assertIn(
            "COLLECT(",
            self.spec_text,
            msg=(
                "memos.spec is missing COLLECT(...) — the build is back to "
                "onefile mode, which crashes with 'semctl: Operation not "
                "permitted' in sandboxed environments (see issue #10)."
            ),
        )

    def test_exe_call_sets_exclude_binaries(self) -> None:
        self.assertIn(
            "exclude_binaries=True",
            self.spec_text,
            msg=(
                "memos.spec's EXE(...) must set exclude_binaries=True so "
                "the runtime deps land inside dist/memos/ instead of being "
                "inlined into a onefile executable."
            ),
        )

    def test_spec_does_not_set_runtime_tmpdir(self) -> None:
        # runtime_tmpdir is an onefile-only argument; its presence signals
        # that the spec has drifted back to onefile mode.
        self.assertNotIn(
            "runtime_tmpdir=",
            self.spec_text,
            msg=(
                "memos.spec must not set runtime_tmpdir — that argument is "
                "onefile-only and its presence signals onefile regression."
            ),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
