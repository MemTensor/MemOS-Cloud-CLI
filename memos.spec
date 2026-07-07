# -*- mode: python ; coding: utf-8 -*-

# NOTE: Do NOT switch this spec back to PyInstaller onefile mode.
# The onefile bootloader allocates a SysV IPC semaphore via
# semget()/semctl() before Python starts. Sandboxes such as Codex
# Desktop deny that syscall class, causing
# "[PYI-...:ERROR] Failed to initialize sync semaphore! semctl:
# Operation not permitted" and aborting before memos_cli.__main__
# runs. Onedir builds skip that syscall path entirely.
# See MemTensor/MemOS-Cloud-CLI issue #10.

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
    upx_exclude=[],
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
