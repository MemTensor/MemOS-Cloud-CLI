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

rm -rf "${BUILD_DIR}" "${DIST_DIR}/memos"
mkdir -p "${STAGE_DIR}" "${DIST_DIR}"

python -m pip install -e "${ROOT_DIR}[build]"
python -m PyInstaller --clean --noconfirm "${ROOT_DIR}/memos.spec"

# PyInstaller onedir produces dist/memos/ (a folder), not dist/memos (a file).
# We stage the folder as-is and archive it under the top-level name "memos/".
if [[ ! -d "${DIST_DIR}/memos" ]]; then
  echo "Expected onedir output at ${DIST_DIR}/memos but did not find it" >&2
  exit 1
fi

cp -R "${DIST_DIR}/memos" "${STAGE_DIR}/memos"
chmod +x "${STAGE_DIR}/memos/memos"

if [[ "${PLATFORM}" == "darwin" ]]; then
  xattr -dr com.apple.quarantine "${STAGE_DIR}/memos" 2>/dev/null || true
fi

tar -czf "${ARCHIVE_PATH}" -C "${STAGE_DIR}" memos

echo "Built binary folder: ${DIST_DIR}/memos"
echo "Built archive: ${ARCHIVE_PATH}"
