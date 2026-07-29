#!/usr/bin/env bash

set -euo pipefail

: "${CURRENT_TAG:?CURRENT_TAG is required}"
: "${TARGET_SHA:?TARGET_SHA is required}"
: "${RECOVER_EXISTING_RELEASE:?RECOVER_EXISTING_RELEASE is required}"
: "${RELEASE_VERSION:?RELEASE_VERSION is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"

git config --local user.name "github-actions[bot]"
git config --local user.email "41898282+github-actions[bot]@users.noreply.github.com"

declare -a release_assets

collect_release_assets() {
  shopt -s nullglob
  release_assets=(dist/*.tar.gz)
  shopt -u nullglob
  if [[ "${#release_assets[@]}" -eq 0 ]]; then
    echo "::error::No dist/*.tar.gz artifacts found; aborting release upload."
    exit 1
  fi
}

ensure_target_is_current_main() {
  local remote_main_sha
  remote_main_sha="$(
    git ls-remote origin "refs/heads/main" |
      awk '$2 == "refs/heads/main" {print $1; exit}'
  )"
  if [[ -z "${remote_main_sha}" ]]; then
    echo "::error::Unable to resolve refs/heads/main immediately before release mutation."
    exit 1
  fi
  if [[ "${remote_main_sha}" != "${TARGET_SHA}" ]]; then
    echo "::error::main moved to ${remote_main_sha} after release inspection; expected ${TARGET_SHA}. Rerun dry_run=true for the new main before creating or updating a Draft Release."
    exit 1
  fi
}

release_notes_file="release-inspection/github-release-notes.md"
if [[ ! -s "${release_notes_file}" ]]; then
  echo "::error::github-release-notes.md is missing or empty."
  exit 1
fi
collect_release_assets

remote_tag_sha="$(
  git ls-remote --tags origin "refs/tags/${CURRENT_TAG}" "refs/tags/${CURRENT_TAG}^{}" |
    awk '$2 ~ /\^\{\}$/ {sha=$1} $2 !~ /\^\{\}$/ && sha=="" {sha=$1} END {print sha}'
)"
if [[ -n "${remote_tag_sha}" && "${remote_tag_sha}" != "${TARGET_SHA}" ]]; then
  echo "::error::${CURRENT_TAG} already exists at ${remote_tag_sha}, expected ${TARGET_SHA}."
  exit 1
fi

release_exists=false
release_info=""
release_lookup_log="${RUNNER_TEMP}/memos-cli-release-lookup-$$.log"
for attempt in 1 2 3; do
  set +e
  release_info="$(
    gh release view "${CURRENT_TAG}" \
      --repo "${GITHUB_REPOSITORY}" \
      --json isDraft,isPrerelease,url \
      --jq '[.isDraft, .isPrerelease, .url] | @tsv' \
      2>"${release_lookup_log}"
  )"
  lookup_status=$?
  set -e
  if [[ "${lookup_status}" == 0 ]]; then
    release_exists=true
    break
  fi
  if grep -Eiq "release not found|HTTP 404|Not Found" "${release_lookup_log}"; then
    break
  fi
  if [[ "${attempt}" == 3 ]]; then
    sed -n '1,80p' "${release_lookup_log}" >&2
    echo "::error::Unable to determine whether ${CURRENT_TAG} already has a GitHub Release."
    exit "${lookup_status}"
  fi
  sleep "$((attempt * 2))"
done

if [[ "${release_exists}" == "true" && -z "${remote_tag_sha}" ]]; then
  echo "::error::GitHub Release ${CURRENT_TAG} exists but its remote tag is missing."
  exit 1
fi
if [[ "${release_exists}" != "true" &&
      -n "${remote_tag_sha}" &&
      "${RECOVER_EXISTING_RELEASE}" != "true" ]]; then
  echo "::error::${CURRENT_TAG} exists without a GitHub Release. Rerun only after reviewing the tag, with recover_existing_release=true."
  exit 1
fi

release_flags=(--draft)
expected_prerelease=false
if [[ "${RELEASE_VERSION}" == *-* ]]; then
  expected_prerelease=true
  release_flags+=(--prerelease)
fi

if [[ "${release_exists}" == "true" ]]; then
  IFS=$'\t' read -r is_draft is_prerelease release_url <<< "${release_info}"
  if [[ "${is_prerelease}" != "${expected_prerelease}" ]]; then
    echo "::error::Existing Release prerelease=${is_prerelease}, expected ${expected_prerelease} for ${CURRENT_TAG}."
    exit 1
  fi
  if [[ "${is_draft}" != "true" ]]; then
    echo "::notice::Published Release already exists at ${release_url}; leaving it unchanged."
    exit 0
  fi

  ensure_target_is_current_main
  gh release upload "${CURRENT_TAG}" "${release_assets[@]}" \
    --repo "${GITHUB_REPOSITORY}" \
    --clobber
  gh release edit "${CURRENT_TAG}" \
    --repo "${GITHUB_REPOSITORY}" \
    --draft \
    --title "MemOS CLI ${CURRENT_TAG}" \
    --notes-file "${release_notes_file}"
else
  ensure_target_is_current_main
  if [[ -z "${remote_tag_sha}" ]]; then
    git tag "${CURRENT_TAG}" "${TARGET_SHA}"
    git push origin "refs/tags/${CURRENT_TAG}"
  else
    echo "::notice::Explicitly recovering the missing GitHub Release for existing tag ${CURRENT_TAG}."
  fi
  gh release create "${CURRENT_TAG}" "${release_assets[@]}" \
    --repo "${GITHUB_REPOSITORY}" \
    --target "${TARGET_SHA}" \
    --title "MemOS CLI ${CURRENT_TAG}" \
    --notes-file "${release_notes_file}" \
    "${release_flags[@]}"
fi

echo "::notice::Draft Release created. Publish the draft manually to emit release.published."
