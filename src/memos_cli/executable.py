"""Resolve the installed MemOS command without relying on the host PATH."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _bundle_root() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parents[2]


def _npm_global_bin_dir() -> Path | None:
    npm_path = shutil.which("npm")
    if not npm_path:
        return None
    try:
        result = subprocess.run(
            [npm_path, "prefix", "-g"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    prefix = result.stdout.strip() if result.returncode == 0 else ""
    return Path(prefix).expanduser() / "bin" if prefix else None


def resolve_memos_executable() -> str | None:
    """Return the absolute platform binary or npm launcher path."""
    candidates: list[Path] = []
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0:
        candidates.append(Path(argv0).expanduser())

    current_bin = Path(sys.executable).resolve().parent
    candidates.extend([current_bin / "memos", current_bin / "memos.exe", current_bin / "memos.js"])

    which_memos = shutil.which("memos")
    if which_memos:
        candidates.append(Path(which_memos).expanduser())

    npm_bin_dir = _npm_global_bin_dir()
    if npm_bin_dir:
        candidates.extend(
            [npm_bin_dir / "memos", npm_bin_dir / "memos.exe", npm_bin_dir / "memos.js"]
        )

    bundle_bin = _bundle_root() / "bin"
    candidates.extend([bundle_bin / "memos", bundle_bin / "memos.exe", bundle_bin / "memos.js"])

    for candidate in candidates:
        if candidate.name.lower() not in {"memos", "memos.exe", "memos.js"}:
            continue
        if candidate.is_file():
            return str(candidate.resolve())
    return None
