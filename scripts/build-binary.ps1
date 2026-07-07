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
$DistMemosDir = Join-Path $DistDir "memos"
if (Test-Path $DistMemosDir) { Remove-Item -Recurse -Force $DistMemosDir }

New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

python -m pip install -e "$RootDir[build]"
python -m PyInstaller --clean --noconfirm "$RootDir\memos.spec"

# memos.spec is now a PyInstaller onedir bundle (see issue #10). Stage
# the whole dist\memos folder and pack it into the archive.
if (-not (Test-Path $DistMemosDir)) {
    throw "PyInstaller did not produce dist\memos\ - expected onedir layout."
}

Copy-Item -Recurse -Force $DistMemosDir (Join-Path $StageDir "memos")
tar -czf $ArchivePath -C $StageDir memos

Write-Host "Built binary tree: $DistMemosDir"
Write-Host "Built archive: $ArchivePath"
