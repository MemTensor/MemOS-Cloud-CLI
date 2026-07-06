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

# NOTE: onedir build (EXE with exclude_binaries=True + COLLECT).
# Onefile builds allocate a SysV IPC semaphore in the bootloader for
# parent/child coordination, which fails with "semctl: Operation not
# permitted" inside sandboxed environments such as Codex Desktop and
# containers without an IPC namespace. Onedir skips the semaphore
# entirely (interpreter runs in-place inside the extracted folder).
# See issue #10.
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
