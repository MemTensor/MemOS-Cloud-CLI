$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Version = python -c "from src.memos_cli import __version__; print(__version__)"
$ArchName = $env:PROCESSOR_ARCHITECTURE

switch ($ArchName.ToUpper()) {
    "AMD64" { $Arch = "x64" }
    "ARM64" { $Arch = "arm64" }
    default { throw "Unsupported architecture: $ArchName" }
}

$Target = "windows-$Arch"
$DistDir = Join-Path $RootDir "dist"
$BuildDir = Join-Path $RootDir "build"
$StageDir = Join-Path $BuildDir "package\$Target"
$ArchiveBaseName = "memos-$Version-$Target"
$ArchivePath = Join-Path $DistDir "$ArchiveBaseName.tar.gz"

if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }
if (Test-Path (Join-Path $DistDir "memos.exe")) { Remove-Item -Force (Join-Path $DistDir "memos.exe") }
if (Test-Path (Join-Path $DistDir "memos")) { Remove-Item -Recurse -Force (Join-Path $DistDir "memos") }

New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

python -m pip install -e "$RootDir[build]"
python -m PyInstaller --clean --noconfirm "$RootDir\memos.spec"

# Onedir layout: memos.spec now runs COLLECT and produces a folder
# at dist/memos/ containing memos.exe plus its runtime deps.
# Ship that folder wholesale — see issue #10 for the semctl story.
$OneDirRoot = Join-Path $DistDir "memos"
if (-not (Test-Path $OneDirRoot -PathType Container)) {
    throw "Expected onedir folder at $OneDirRoot but none found. Did memos.spec revert to onefile? See issue #10."
}

# Copy-Item -Recurse into an already-existing destination nests the
# source *inside* it (e.g. StageDir\memos\memos\*), which breaks the
# tar layout and postinstall extraction. Wipe any prior destination
# so the copy is idempotent across partial re-runs.
$StageMemos = Join-Path $StageDir "memos"
if (Test-Path $StageMemos) { Remove-Item -Recurse -Force $StageMemos }
Copy-Item -Recurse $OneDirRoot $StageMemos
tar -czf $ArchivePath -C $StageDir memos

Write-Host "Built onedir bundle: $(Join-Path $DistDir 'memos')"
Write-Host "Built archive: $ArchivePath"
