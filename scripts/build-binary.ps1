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

New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

python -m pip install -e "$RootDir[build]"
python -m PyInstaller --clean --noconfirm "$RootDir\memos.spec"

Copy-Item (Join-Path $DistDir "memos.exe") (Join-Path $StageDir "memos.exe")
tar -czf $ArchivePath -C $StageDir memos.exe

Write-Host "Built binary: $(Join-Path $DistDir 'memos.exe')"
Write-Host "Built archive: $ArchivePath"
