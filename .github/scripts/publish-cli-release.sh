#!/usr/bin/env bash

set -euo pipefail

: "${CURRENT_TAG:?CURRENT_TAG is required}"
: "${TARGET_SHA:?TARGET_SHA is required}"
: "${RECOVER_EXISTING_RELEASE:?RECOVER_EXISTING_RELEASE is required}"
: "${RELEASE_VERSION:?RELEASE_VERSION is required}"
: "${RELEASE_SOURCE_MODE:?RELEASE_SOURCE_MODE is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"

npm_version_exists="${NPM_VERSION_EXISTS:-false}"
npm_git_head="${NPM_GIT_HEAD:-}"
package_name="@memtensor/memos-cloud-cli"
if [[ "${npm_version_exists}" != "true" && "${npm_version_exists}" != "false" ]]; then
  echo "::error::NPM_VERSION_EXISTS must be true or false."
  exit 1
fi

query_live_npm_state() {
  local attempt status payload parsed
  local lookup_log="${RUNNER_TEMP}/memos-cli-npm-state-$$.log"
  live_npm_git_head=""
  for ((attempt = 1; attempt <= 3; attempt += 1)); do
    if payload="$(npm view "${package_name}@${RELEASE_VERSION}" version gitHead --json 2>"${lookup_log}")"; then
      status=0
    else
      status=$?
    fi
    if [[ "${status}" == 0 ]]; then
      if parsed="$(node -e '
        const payload = JSON.parse(process.argv[1] || "{}");
        if (!payload || typeof payload !== "object" || Array.isArray(payload)) process.exit(2);
        process.stdout.write(String(payload.gitHead || ""));
      ' "${payload}" 2>>"${lookup_log}")"; then
        status=0
      else
        status=$?
      fi
      if [[ "${status}" != 0 ]]; then
        sed -n '1,80p' "${lookup_log}" >&2
        echo "::error::npm returned an invalid state payload for ${package_name}@${RELEASE_VERSION}."
        return 2
      fi
      live_npm_git_head="${parsed}"
      return 0
    fi
    if grep -Eiq "E404|404 Not Found|No match found|is not in this registry" "${lookup_log}"; then
      return 1
    fi
    if [[ "${attempt}" == 3 ]]; then
      sed -n '1,80p' "${lookup_log}" >&2
      echo "::error::Failed to recheck ${package_name}@${RELEASE_VERSION} immediately before GitHub release mutation."
      return 2
    fi
    retry_sleep "${attempt}"
  done
}

git config --local user.name "github-actions[bot]"
git config --local user.email "41898282+github-actions[bot]@users.noreply.github.com"

declare -a release_assets

case "${RELEASE_SOURCE_MODE}" in
  manual_dispatch|trusted_main_push) ;;
  *)
    echo "::error::Unknown RELEASE_SOURCE_MODE: ${RELEASE_SOURCE_MODE}"
    exit 1
    ;;
esac

release_retry_attempts="${RELEASE_RETRY_ATTEMPTS:-6}"
release_retry_sleep_seconds="${RELEASE_RETRY_SLEEP_SECONDS:-}"
if [[ ! "${release_retry_attempts}" =~ ^[1-9][0-9]*$ ||
      "${release_retry_attempts}" -gt 10 ]]; then
  echo "::error::RELEASE_RETRY_ATTEMPTS must be an integer from 1 to 10."
  exit 1
fi
if [[ -n "${release_retry_sleep_seconds}" &&
      ! "${release_retry_sleep_seconds}" =~ ^[0-9]+$ ]]; then
  echo "::error::RELEASE_RETRY_SLEEP_SECONDS must be a non-negative integer when set."
  exit 1
fi

retry_sleep() {
  local attempt="$1"
  local delay
  if [[ -n "${release_retry_sleep_seconds}" ]]; then
    delay="${release_retry_sleep_seconds}"
  else
    delay=$((2 << (attempt - 1)))
    if [[ "${delay}" -gt 30 ]]; then
      delay=30
    fi
  fi
  if [[ "${delay}" -gt 0 ]]; then
    sleep "${delay}"
  fi
}

run_retryable_command() {
  local description="$1"
  shift
  local attempt status
  local retry_log="${RUNNER_TEMP}/memos-cli-release-command-$$.log"
  for ((attempt = 1; attempt <= release_retry_attempts; attempt += 1)); do
    set +e
    "$@" 2>"${retry_log}"
    status=$?
    set -e
    if [[ "${status}" == 0 ]]; then
      return 0
    fi
    if [[ "${attempt}" == "${release_retry_attempts}" ]]; then
      sed -n '1,80p' "${retry_log}" >&2
      echo "::error::${description} failed after ${attempt} attempts."
      return "${status}"
    fi
    echo "::warning::${description} failed on attempt ${attempt}; retrying."
    retry_sleep "${attempt}"
  done
}

resolve_remote_main() {
  local attempt status output
  local lookup_log="${RUNNER_TEMP}/memos-cli-main-lookup-$$.log"
  for ((attempt = 1; attempt <= release_retry_attempts; attempt += 1)); do
    set +e
    output="$(git ls-remote origin "refs/heads/main" 2>"${lookup_log}")"
    status=$?
    set -e
    if [[ "${status}" == 0 ]]; then
      awk '$2 == "refs/heads/main" {print $1; exit}' <<< "${output}"
      return 0
    fi
    if [[ "${attempt}" == "${release_retry_attempts}" ]]; then
      sed -n '1,80p' "${lookup_log}" >&2
      return "${status}"
    fi
    retry_sleep "${attempt}"
  done
}

resolve_remote_tag() {
  local wait_for_visibility="${1:-false}"
  local attempt status output remote_sha
  local lookup_log="${RUNNER_TEMP}/memos-cli-tag-lookup-$$.log"
  for ((attempt = 1; attempt <= release_retry_attempts; attempt += 1)); do
    set +e
    output="$(
      git ls-remote --tags origin "refs/tags/${CURRENT_TAG}" "refs/tags/${CURRENT_TAG}^{}" \
        2>"${lookup_log}"
    )"
    status=$?
    set -e
    if [[ "${status}" == 0 ]]; then
      remote_sha="$(
        awk '$2 ~ /\^\{\}$/ {sha=$1} $2 !~ /\^\{\}$/ && sha=="" {sha=$1} END {print sha}' \
          <<< "${output}"
      )"
      if [[ -n "${remote_sha}" || "${wait_for_visibility}" != "true" ]]; then
        printf '%s\n' "${remote_sha}"
        return 0
      fi
    elif [[ "${attempt}" == "${release_retry_attempts}" ]]; then
      sed -n '1,80p' "${lookup_log}" >&2
      return "${status}"
    fi
    if [[ "${attempt}" != "${release_retry_attempts}" ]]; then
      retry_sleep "${attempt}"
    fi
  done
  return 0
}

release_exists=false
release_info=""
release_assets_info=""
all_release_assets_visible() {
  local asset asset_name
  for asset in "${release_assets[@]}"; do
    asset_name="${asset##*/}"
    if [[ ",${release_assets_info}," != *",${asset_name},"* ]]; then
      return 1
    fi
  done
}

lookup_release() {
  local wait_for_visibility="${1:-false}"
  local wait_for_assets="${2:-false}"
  local attempt lookup_status
  local release_lookup_log="${RUNNER_TEMP}/memos-cli-release-lookup-$$.log"
  release_exists=false
  release_info=""
  release_assets_info=""
  for ((attempt = 1; attempt <= release_retry_attempts; attempt += 1)); do
    set +e
    release_info="$(
      gh release view "${CURRENT_TAG}" \
        --repo "${GITHUB_REPOSITORY}" \
        --json isDraft,isPrerelease,url,assets \
        --jq '[.isDraft, .isPrerelease, .url, ([.assets[].name] | sort | join(","))] | @tsv' \
        2>"${release_lookup_log}"
    )"
    lookup_status=$?
    set -e
    if [[ "${lookup_status}" == 0 ]]; then
      release_exists=true
      IFS=$'\t' read -r _ _ _ release_assets_info <<< "${release_info}"
      if [[ "${wait_for_assets}" != "true" ]] || all_release_assets_visible; then
        return 0
      fi
      if [[ "${attempt}" == "${release_retry_attempts}" ]]; then
        return 0
      fi
    elif grep -Eiq "release not found|HTTP 404|Not Found" "${release_lookup_log}"; then
      if [[ "${wait_for_visibility}" != "true" ]]; then
        return 0
      fi
    elif [[ "${attempt}" == "${release_retry_attempts}" ]]; then
      sed -n '1,80p' "${release_lookup_log}" >&2
      echo "::error::Unable to determine whether ${CURRENT_TAG} has a GitHub Release."
      return "${lookup_status}"
    fi
    if [[ "${attempt}" != "${release_retry_attempts}" ]]; then
      retry_sleep "${attempt}"
    fi
  done
}

validate_draft_metadata() {
  local is_draft is_prerelease release_url ignored_assets
  if [[ "${release_exists}" != "true" ]]; then
    return 1
  fi
  IFS=$'\t' read -r is_draft is_prerelease release_url ignored_assets <<< "${release_info}"
  if [[ "${is_prerelease}" != "${expected_prerelease}" ]]; then
    echo "::error::Release prerelease=${is_prerelease}, expected ${expected_prerelease} for ${CURRENT_TAG}."
    return 1
  fi
  if [[ "${is_draft}" != "true" ]]; then
    echo "::error::Expected ${CURRENT_TAG} to remain a Draft Release, but found ${release_url}."
    return 1
  fi
}

validate_draft_release() {
  validate_draft_metadata || return 1
  if ! all_release_assets_visible; then
    echo "::error::Draft Release ${CURRENT_TAG} is missing one or more expected build assets."
    return 1
  fi
}

upload_and_update_draft() {
  run_retryable_command \
    "Uploading assets to Draft Release ${CURRENT_TAG}" \
    gh release upload "${CURRENT_TAG}" "${release_assets[@]}" \
      --repo "${GITHUB_REPOSITORY}" \
      --clobber
  run_retryable_command \
    "Updating Draft Release ${CURRENT_TAG}" \
    gh release edit "${CURRENT_TAG}" \
      --repo "${GITHUB_REPOSITORY}" \
      --draft \
      --title "MemOS CLI ${CURRENT_TAG}" \
      --notes-file "${release_notes_file}"
}

collect_release_assets() {
  shopt -s nullglob
  release_assets=(dist/*.tar.gz)
  shopt -u nullglob
  if [[ "${#release_assets[@]}" -eq 0 ]]; then
    echo "::error::No dist/*.tar.gz artifacts found; aborting release upload."
    exit 1
  fi
}

ensure_target_is_allowed_main_source() {
  local remote_main_sha
  remote_main_sha="$(resolve_remote_main)"
  if [[ -z "${remote_main_sha}" ]]; then
    echo "::error::Unable to resolve refs/heads/main immediately before release mutation."
    exit 1
  fi
  if [[ "${RELEASE_SOURCE_MODE}" == "trusted_main_push" ]]; then
    git fetch --no-tags origin "+refs/heads/main:refs/remotes/origin/main"
    if ! git merge-base --is-ancestor "${TARGET_SHA}" "${remote_main_sha}"; then
      echo "::error::Trusted main push target ${TARGET_SHA} is not contained in current main ${remote_main_sha}. Refusing to create or update a Draft Release."
      exit 1
    fi
    return 0
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

set +e
query_live_npm_state
live_npm_status=$?
set -e
if [[ "${live_npm_status}" == 2 ]]; then
  exit 1
fi
if [[ "${npm_version_exists}" == "false" && "${live_npm_status}" == 0 ]]; then
  echo "::error::npm state changed after release inspection: ${package_name}@${RELEASE_VERSION} now exists. Rerun the workflow so recovery can verify its immutable gitHead."
  exit 1
fi
if [[ "${npm_version_exists}" == "true" && "${live_npm_status}" != 0 ]]; then
  echo "::error::npm state changed after release inspection: expected ${package_name}@${RELEASE_VERSION} to exist. Refusing recovery."
  exit 1
fi
if [[ "${npm_version_exists}" == "true" && "${live_npm_git_head}" != "${npm_git_head}" ]]; then
  echo "::error::npm gitHead changed after release inspection: expected ${npm_git_head}, got ${live_npm_git_head:-missing}. Refusing recovery."
  exit 1
fi

if [[ "${npm_version_exists}" == "true" ]]; then
  if [[ "${RECOVER_EXISTING_RELEASE}" != "true" ]]; then
    echo "::error::npm already contains ${RELEASE_VERSION}; explicit recover_existing_release=true is required before any GitHub release mutation."
    exit 1
  fi
  if [[ ! "${npm_git_head}" =~ ^[0-9a-fA-F]{40}$ ]]; then
    echo "::error::npm already contains ${RELEASE_VERSION}, but npm gitHead is missing or invalid. Refusing recovery."
    exit 1
  fi
  if [[ "${npm_git_head}" != "${TARGET_SHA}" ]]; then
    echo "::error::npm ${RELEASE_VERSION} points to ${npm_git_head}, expected immutable release target ${TARGET_SHA}. Refusing recovery."
    exit 1
  fi
  echo "::notice::Verified existing npm ${RELEASE_VERSION} at ${TARGET_SHA}; continuing explicit GitHub metadata recovery."
fi

remote_tag_sha="$(resolve_remote_tag false)"
if [[ -n "${remote_tag_sha}" && "${remote_tag_sha}" != "${TARGET_SHA}" ]]; then
  echo "::error::${CURRENT_TAG} already exists at ${remote_tag_sha}, expected ${TARGET_SHA}."
  exit 1
fi

if [[ -n "${remote_tag_sha}" ]]; then
  # A previous attempt may have created the Release just before its response was
  # interrupted. Give that Release time to become visible before calling the tag
  # orphaned and requiring explicit recovery.
  lookup_release true false
else
  lookup_release false false
fi

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
  IFS=$'\t' read -r is_draft is_prerelease release_url _ <<< "${release_info}"
  if [[ "${is_prerelease}" != "${expected_prerelease}" ]]; then
    echo "::error::Existing Release prerelease=${is_prerelease}, expected ${expected_prerelease} for ${CURRENT_TAG}."
    exit 1
  fi
  if [[ "${is_draft}" != "true" ]]; then
    echo "::notice::Published Release already exists at ${release_url}; leaving it unchanged."
    exit 0
  fi

  ensure_target_is_allowed_main_source
  upload_and_update_draft
  lookup_release true true
  if ! validate_draft_release; then
    echo "::error::Draft Release ${CURRENT_TAG} could not be verified after update."
    exit 1
  fi
else
  ensure_target_is_allowed_main_source
  if [[ -z "${remote_tag_sha}" ]]; then
    git tag "${CURRENT_TAG}" "${TARGET_SHA}"
    tag_push_log="${RUNNER_TEMP}/memos-cli-tag-push-$$.log"
    set +e
    git push origin "refs/tags/${CURRENT_TAG}" 2>"${tag_push_log}"
    tag_push_status=$?
    set -e
    remote_tag_sha="$(resolve_remote_tag true)"
    if [[ -z "${remote_tag_sha}" ]]; then
      if [[ "${tag_push_status}" != 0 ]]; then
        sed -n '1,80p' "${tag_push_log}" >&2
      fi
      echo "::error::Tag push returned status ${tag_push_status}, but ${CURRENT_TAG} was not visible on origin after ${release_retry_attempts} checks. Refusing to issue a second push or create a Release from an unverified tag."
      if [[ "${tag_push_status}" != 0 ]]; then
        exit "${tag_push_status}"
      fi
      exit 1
    fi
    if [[ "${remote_tag_sha}" != "${TARGET_SHA}" ]]; then
      echo "::error::Remote ${CURRENT_TAG} resolved to ${remote_tag_sha} after push, expected ${TARGET_SHA}."
      exit 1
    fi
    if [[ "${tag_push_status}" != 0 ]]; then
      echo "::notice::Tag push returned an error, but origin now contains the expected immutable tag; continuing without pushing twice."
    fi
  else
    echo "::notice::Explicitly recovering the missing GitHub Release for existing tag ${CURRENT_TAG}."
  fi
  release_create_log="${RUNNER_TEMP}/memos-cli-release-create-$$.log"
  set +e
  gh release create "${CURRENT_TAG}" "${release_assets[@]}" \
    --repo "${GITHUB_REPOSITORY}" \
    --target "${TARGET_SHA}" \
    --title "MemOS CLI ${CURRENT_TAG}" \
    --notes-file "${release_notes_file}" \
    --verify-tag \
    "${release_flags[@]}" \
    2>"${release_create_log}"
  release_create_status=$?
  set -e

  # A create request can succeed server-side before the new Release is visible
  # to a following read. Poll instead of issuing a second create request.
  lookup_release true true
  if [[ "${release_exists}" == "true" ]]; then
    if ! validate_draft_metadata; then
      exit 1
    fi
    if ! all_release_assets_visible; then
      echo "::warning::Draft Release ${CURRENT_TAG} exists but its assets are incomplete; safely resuming the Draft upload instead of creating another Release."
      upload_and_update_draft
      lookup_release true true
    fi
    validate_draft_release
  elif [[ "${release_create_status}" != 0 ]]; then
    sed -n '1,80p' "${release_create_log}" >&2
    echo "::error::GitHub Release creation returned an error and no matching Draft became visible. The tag was not changed; inspect GitHub before rerunning with recover_existing_release=true."
    exit "${release_create_status}"
  else
    echo "::error::GitHub Release creation returned success, but ${CURRENT_TAG} was not visible after ${release_retry_attempts} checks. Refusing to issue a second create request; inspect GitHub before rerunning."
    exit 1
  fi
fi

echo "::notice::Draft Release created. Publish the draft manually to emit release.published."
