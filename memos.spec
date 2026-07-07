# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH)
datas = [
    (
        str(project_root / "src" / "memos_cli" / "templates" / "agent_guidance.md"),
        "memos_cli/templates",
    ),
    (
        str(project_root / "skills" / "memos-memory"),
        "skills/memos-memory",
    ),
]

analysis = Analysis(
    ["src/memos_cli/__main__.py"],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["click"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

# NOTE: This spec is intentionally **onedir**, not onefile.
#
# PyInstaller's onefile bootloader allocates a SysV IPC semaphore
# (semget / semctl) to synchronise the parent bootloader with the
# extracted child interpreter. Sandboxed environments such as Codex
# Desktop and hardened seccomp profiles deny that syscall class and
# the bootloader aborts before Python starts, printing
# "semctl: Operation not permitted". Onedir builds run the interpreter
# in-place and never touch semget/semctl, which is the upstream
# recommended remedy for the "semctl: Operation not permitted" crash.
#
# If you're tempted to inline the binaries/datas into EXE(...) again
# (i.e. revert to onefile) or add the onefile-only tmpdir argument to
# EXE(...), please read issue #10 and
# openspec/changes/2026-07-07-10-.../design.md first.
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="memos",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="memos",
)
