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

# memos.spec is now a PyInstaller **onedir** bundle (see issue #10 —
# onefile bootloader crashes in Codex Desktop with
# "semctl: Operation not permitted"). PyInstaller drops the whole
# runtime tree under dist/memos/; we stage that folder verbatim into
# the archive.
if [[ ! -d "${ROOT_DIR}/dist/memos" ]]; then
  echo "PyInstaller did not produce dist/memos/ — expected onedir layout." >&2
  exit 1
fi

cp -R "${ROOT_DIR}/dist/memos" "${STAGE_DIR}/memos"
chmod +x "${STAGE_DIR}/memos/memos"
# cp -R preserves the source permission bits, so bundled shared libraries
# (.so on Linux, .dylib on macOS) usually stay executable. However, if the
# build agent's umask is stricter than 022 (e.g. 027), the execute bit can
# be silently stripped and the dynamic linker will fail at runtime with an
# opaque error. Restore +x explicitly to keep the archive portable.
find "${STAGE_DIR}/memos" \( -name '*.so' -o -name '*.so.*' -o -name '*.dylib' \) \
  -exec chmod +x {} + 2>/dev/null || true

# macOS quarantine strip: copy first, then clear com.apple.quarantine on
# the *staged* tree. Any step that touches the staged files after this
# (signing, notarisation) should re-run the strip — otherwise stale
# attributes can propagate into the tarball and users see Gatekeeper
# blocks on first run.
if [[ "${PLATFORM}" == "darwin" ]]; then
  xattr -dr com.apple.quarantine "${STAGE_DIR}/memos" 2>/dev/null || true
fi

tar -czf "${ARCHIVE_PATH}" -C "${STAGE_DIR}" memos

echo "Built binary tree: ${ROOT_DIR}/dist/memos/"
echo "Built archive: ${ARCHIVE_PATH}"
