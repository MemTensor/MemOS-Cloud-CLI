#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(python -c 'from src.memos_cli import __version__; print(__version__)')"

OS_NAME="$(uname -s)"
ARCH_NAME="$(uname -m)"

case "${OS_NAME}" in
  Darwin) PLATFORM="darwin" ;;
  Linux) PLATFORM="linux" ;;
  *)
    echo "Unsupported operating system: ${OS_NAME}" >&2
    exit 1
    ;;
esac

case "${ARCH_NAME}" in
  arm64|aarch64) ARCH="arm64" ;;
  x86_64|amd64) ARCH="x64" ;;
  *)
    echo "Unsupported architecture: ${ARCH_NAME}" >&2
    exit 1
    ;;
esac

TARGET="${PLATFORM}-${ARCH}"
DIST_DIR="${ROOT_DIR}/dist"
BUILD_DIR="${ROOT_DIR}/build"
STAGE_DIR="${BUILD_DIR}/package/${TARGET}"
ARCHIVE_BASENAME="memos-${VERSION}-${TARGET}"
ARCHIVE_PATH="${DIST_DIR}/${ARCHIVE_BASENAME}.tar.gz"

rm -rf "${BUILD_DIR}" "${ROOT_DIR}/dist/memos"
mkdir -p "${STAGE_DIR}" "${DIST_DIR}"

python -m pip install -e "${ROOT_DIR}[build]"
python -m PyInstaller --clean --noconfirm "${ROOT_DIR}/memos.spec"

# Onedir layout: memos.spec now runs COLLECT and produces a folder
# at dist/memos/ containing the executable plus its runtime deps.
# Ship that folder wholesale — see issue #10 for the semctl story.
if [[ ! -d "${ROOT_DIR}/dist/memos" ]]; then
  echo "Expected onedir folder at ${ROOT_DIR}/dist/memos but none found." >&2
  echo "Did memos.spec revert to onefile? See issue #10." >&2
  exit 1
fi

# Two-step to keep the copy fully idempotent across partial re-runs:
# `rm -rf` unambiguously wipes any leftover destination first (a
# stale run that cleaned dist/memos but not ${BUILD_DIR} could leave
# ${STAGE_DIR}/memos around), then the trailing slash on the source
# guarantees `cp -R` copies the *contents* even if a race recreates
# the destination between the two commands. Without either, a
# leftover directory ends up doubly-nested at ${STAGE_DIR}/memos/memos/
# and the chmod on the next line would target a directory and blow
# up under `set -euo pipefail`.
rm -rf "${STAGE_DIR}/memos"
cp -R "${ROOT_DIR}/dist/memos/" "${STAGE_DIR}/memos"
chmod +x "${STAGE_DIR}/memos/memos"

if [[ "${PLATFORM}" == "darwin" ]]; then
  xattr -dr com.apple.quarantine "${STAGE_DIR}/memos" 2>/dev/null || true
fi

tar -czf "${ARCHIVE_PATH}" -C "${STAGE_DIR}" memos

echo "Built onedir bundle: ${ROOT_DIR}/dist/memos"
echo "Built archive: ${ARCHIVE_PATH}"
