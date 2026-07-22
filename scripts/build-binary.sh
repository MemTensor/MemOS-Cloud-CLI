#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_VENV="${MEMOS_BUILD_VENV:-${ROOT_DIR}/.venv-build}"
BUILD_PYTHON="${BUILD_VENV}/bin/python"

find_base_python() {
  local candidate

  if [[ -n "${MEMOS_BUILD_BASE_PYTHON:-}" ]]; then
    if "${MEMOS_BUILD_BASE_PYTHON}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
      printf '%s\n' "${MEMOS_BUILD_BASE_PYTHON}"
      return 0
    fi

    echo "MEMOS_BUILD_BASE_PYTHON must point to Python >= 3.10" >&2
    return 1
  fi

  for candidate in python3.13 python3.12 python3.11 python3.10 python python3; do
    if command -v "${candidate}" >/dev/null 2>&1 &&
      "${candidate}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  echo "Python >= 3.10 is required to build the MemOS CLI binary." >&2
  return 1
}

if [[ -x "${BUILD_PYTHON}" ]] && ! "${BUILD_PYTHON}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null; then
  echo "Existing build venv Python is unusable or does not satisfy >= 3.10; recreating..." >&2
  if [[ -z "${BUILD_VENV}" || "${BUILD_VENV}" == "/" ]]; then
    echo "Refusing to remove unsafe build venv path: ${BUILD_VENV:-<empty>}" >&2
    exit 1
  fi
  rm -rf "${BUILD_VENV}"
fi

if [[ ! -x "${BUILD_PYTHON}" ]]; then
  BASE_PYTHON="$(find_base_python)"
  "${BASE_PYTHON}" -m venv "${BUILD_VENV}"
fi

VERSION="$(PYTHONPATH="${ROOT_DIR}" "${BUILD_PYTHON}" -c 'from src.memos_cli import __version__; print(__version__)')"

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

"${BUILD_PYTHON}" -m pip install --upgrade pip
"${BUILD_PYTHON}" -m pip install -e "${ROOT_DIR}[build]"
"${BUILD_PYTHON}" -m PyInstaller --clean --noconfirm "${ROOT_DIR}/memos.spec"

cp "${ROOT_DIR}/dist/memos" "${STAGE_DIR}/memos"
chmod +x "${STAGE_DIR}/memos"

if [[ "${PLATFORM}" == "darwin" ]]; then
  xattr -dr com.apple.quarantine "${STAGE_DIR}/memos" 2>/dev/null || true
fi

LC_ALL=C tar -czf "${ARCHIVE_PATH}" -C "${STAGE_DIR}" memos

echo "Built binary: ${ROOT_DIR}/dist/memos"
echo "Built archive: ${ARCHIVE_PATH}"
