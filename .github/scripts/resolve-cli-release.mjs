#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { appendFileSync, readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

import { compareSemver, parseSemver } from "./prepare-cli-release.mjs";

export const VERSION_FILES = [
  "package.json",
  "pyproject.toml",
  "src/memos_cli/__init__.py",
];

const PACKAGE_NAME = "@memtensor/memos-cloud-cli";
const TRUSTED_REPOSITORY = "MemTensor/MemOS-Cloud-CLI";

function clean(value) {
  return String(value ?? "").trim();
}

function exactSha(value) {
  return /^[0-9a-fA-F]{40}$/.test(clean(value));
}

export function automaticRecoveryRequested(runAttempt) {
  return /^(?:[2-9]|[1-9][0-9]+)$/.test(clean(runAttempt));
}

function git(args, { cwd = process.cwd() } = {}) {
  return execFileSync("git", args, {
    cwd,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function versionFromText(file, text) {
  if (file === "package.json") {
    return clean(JSON.parse(text).version);
  }
  if (file === "pyproject.toml") {
    return clean(text.match(/^version\s*=\s*["']([^"']+)["']/m)?.[1]);
  }
  return clean(text.match(/^__version__\s*=\s*["']([^"']+)["']/m)?.[1]);
}

export function versionsFromGitRef(ref, root = process.cwd()) {
  const sourceRef = clean(ref);
  if (!sourceRef) throw new Error("a git ref is required to read CLI versions");
  return Object.fromEntries(
    VERSION_FILES.map((file) => {
      const text = git(["show", `${sourceRef}:${file}`], { cwd: root });
      return [file, versionFromText(file, text)];
    }),
  );
}

export function changedFilesFromGitRange(
  baseRef,
  targetRef,
  root = process.cwd(),
) {
  const output = git(
    ["diff", "--name-only", baseRef, targetRef, "--", ...VERSION_FILES],
    { cwd: root },
  );
  return output ? output.split("\n").map(clean).filter(Boolean) : [];
}

function commonVersion(versions, label) {
  const missing = VERSION_FILES.filter((file) => !clean(versions?.[file]));
  if (missing.length) {
    return {
      ok: false,
      reason: `${label} is missing a version in ${missing.join(", ")}`,
    };
  }
  const unique = [...new Set(VERSION_FILES.map((file) => clean(versions[file])))];
  if (unique.length !== 1) {
    return {
      ok: false,
      reason: `${label} has inconsistent versions: ${VERSION_FILES.map(
        (file) => `${file}=${clean(versions[file]) || "missing"}`,
      ).join(", ")}`,
    };
  }
  return { ok: true, version: unique[0] };
}

export function inspectVersionTransition({
  previousVersions,
  currentVersions,
  changedFiles,
}) {
  const changedVersionValues = VERSION_FILES.filter(
    (file) => clean(previousVersions?.[file]) !== clean(currentVersions?.[file]),
  );
  if (changedVersionValues.length === 0) {
    return {
      ok: true,
      eligible: false,
      reason: "the main push did not change the CLI release version",
      changed_version_files: [],
    };
  }

  const previous = commonVersion(previousVersions, "the pre-merge main source");
  if (!previous.ok) {
    return {
      ...previous,
      eligible: false,
      changed_version_files: changedVersionValues,
    };
  }
  const actualChanged = new Set((changedFiles || []).map(clean));
  const missingFromPr = VERSION_FILES.filter(
    (file) =>
      !changedVersionValues.includes(file) || !actualChanged.has(file),
  );
  if (missingFromPr.length) {
    return {
      ok: false,
      eligible: false,
      reason: `the release version changed, but all three version files were not updated by this main push; missing or unchanged: ${missingFromPr.join(", ")}`,
      previous_version: previous.version,
      version: clean(currentVersions?.["package.json"]),
      changed_version_files: changedVersionValues,
    };
  }

  const current = commonVersion(currentVersions, "the merged main source");
  if (!current.ok) {
    return {
      ...current,
      eligible: false,
      previous_version: previous.version,
      changed_version_files: changedVersionValues,
    };
  }

  if (!parseSemver(previous.version) || !parseSemver(current.version)) {
    return {
      ok: false,
      eligible: false,
      reason: `CLI release versions must be strict SemVer; got ${previous.version} -> ${current.version}`,
      previous_version: previous.version,
      version: current.version,
      changed_version_files: changedVersionValues,
    };
  }
  if (previous.version.includes("+") || current.version.includes("+")) {
    return {
      ok: false,
      eligible: false,
      reason:
        "automatic CLI releases reject SemVer build metadata because immutable v-tags would have equal precedence",
      previous_version: previous.version,
      version: current.version,
      changed_version_files: changedVersionValues,
    };
  }
  if (compareSemver(current.version, previous.version) <= 0) {
    return {
      ok: false,
      eligible: false,
      reason: `CLI release version must increase by SemVer precedence; got ${previous.version} -> ${current.version}`,
      previous_version: previous.version,
      version: current.version,
      changed_version_files: changedVersionValues,
    };
  }

  return {
    ok: true,
    eligible: true,
    reason: `all three committed CLI versions increased from ${previous.version} to ${current.version}`,
    previous_version: previous.version,
    version: current.version,
    changed_version_files: [...VERSION_FILES],
  };
}

export function inspectMainPushEvent({
  eventName,
  repository,
  ref,
  beforeSha,
  afterSha,
}) {
  if (eventName === "workflow_dispatch") {
    return { ok: true, inspect: false, reason: "manual workflow dispatch" };
  }
  if (eventName !== "push") {
    return {
      ok: true,
      inspect: false,
      reason: `unsupported automatic release event: ${clean(eventName) || "unknown"}`,
    };
  }
  if (clean(repository) !== TRUSTED_REPOSITORY) {
    return {
      ok: true,
      inspect: false,
      reason: "automatic CLI releases only run for the official repository",
    };
  }
  if (clean(ref) !== "refs/heads/main") {
    return {
      ok: true,
      inspect: false,
      reason: `push targets ${clean(ref) || "an unknown ref"}, not refs/heads/main`,
    };
  }
  if (
    !exactSha(beforeSha) ||
    !exactSha(afterSha) ||
    /^0{40}$/.test(clean(beforeSha)) ||
    /^0{40}$/.test(clean(afterSha)) ||
    clean(beforeSha) === clean(afterSha)
  ) {
    return {
      ok: false,
      inspect: false,
      reason:
        "main push must provide distinct, non-zero 40-character before and after commit SHAs",
    };
  }
  return {
    ok: true,
    inspect: true,
    reason:
      "official main advanced; inspect the committed version transition after the reviewed merge",
  };
}

export function validateAutomaticRelease({
  eventName,
  repository,
  ref,
  beforeSha,
  afterSha,
  previousVersions,
  currentVersions,
  changedFiles,
}) {
  const event = inspectMainPushEvent({
    eventName,
    repository,
    ref,
    beforeSha,
    afterSha,
  });
  if (!event.ok || !event.inspect) return { ...event, eligible: false };
  const transition = inspectVersionTransition({
    previousVersions,
    currentVersions,
    changedFiles,
  });
  return {
    ...transition,
    inspect: true,
    target_sha: clean(afterSha),
    base_sha: clean(beforeSha),
  };
}

export function applyNpmRegistryGuard({
  result,
  npmState,
  recoveryAuthorized = false,
}) {
  if (!result?.eligible) return result;
  if (!npmState?.exists) {
    return {
      ...result,
      npm_version_exists: false,
      npm_git_head: "",
      recovery_required: false,
    };
  }
  const npmGitHead = clean(npmState.gitHead);
  if (!exactSha(npmGitHead)) {
    return {
      ...result,
      ok: false,
      eligible: false,
      npm_version_exists: true,
      npm_git_head: npmGitHead,
      recovery_required: true,
      reason: `${PACKAGE_NAME}@${result.version} already exists but has no trustworthy 40-character npm gitHead; refusing automatic GitHub metadata creation`,
    };
  }
  if (npmGitHead !== clean(result.target_sha)) {
    return {
      ...result,
      ok: false,
      eligible: false,
      npm_version_exists: true,
      npm_git_head: npmGitHead,
      recovery_required: true,
      reason: `${PACKAGE_NAME}@${result.version} records npm gitHead ${npmGitHead}, not the trusted main commit ${clean(result.target_sha)}; refusing to move or invent release metadata`,
    };
  }
  if (recoveryAuthorized) {
    return {
      ...result,
      ok: true,
      eligible: true,
      npm_version_exists: true,
      npm_git_head: npmGitHead,
      recovery_required: true,
      reason: `${PACKAGE_NAME}@${result.version} already exists at the trusted main commit; this explicit workflow rerun may reconcile missing GitHub metadata without republishing npm`,
    };
  }
  return {
    ...result,
    ok: false,
    eligible: false,
    npm_version_exists: true,
    npm_git_head: npmGitHead,
    recovery_required: true,
    reason: `${PACKAGE_NAME}@${result.version} already exists at the trusted main commit; inspect npm, tag, and GitHub Release state, then use the manual recovery input if GitHub metadata is incomplete`,
  };
}

export function applyManualNpmRecoveryGuard({ result, npmState }) {
  if (String(result?.dry_run) === "true" || !npmState?.exists) {
    return {
      ...result,
      npm_version_exists: false,
      npm_git_head: "",
      recovery_required: false,
    };
  }
  const npmGitHead = clean(npmState.gitHead);
  if (!exactSha(npmGitHead)) {
    return {
      ...result,
      ok: false,
      eligible: false,
      npm_version_exists: true,
      npm_git_head: npmGitHead,
      recovery_required: true,
      reason: `${PACKAGE_NAME}@${result.version} already exists but has no trustworthy 40-character npm gitHead; refusing manual release mutation`,
    };
  }
  if (String(result.recover_existing_release) !== "true") {
    return {
      ...result,
      ok: false,
      eligible: false,
      npm_version_exists: true,
      npm_git_head: npmGitHead,
      recovery_required: true,
      reason: `${PACKAGE_NAME}@${result.version} already exists; inspect npm, tag, and GitHub Release state, then explicitly enable recover_existing_release`,
    };
  }
  return {
    ...result,
    npm_version_exists: true,
    npm_git_head: npmGitHead,
    recovery_required: true,
    reason: `manual recovery authorized for existing ${PACKAGE_NAME}@${result.version}; the publish job must still prove npm gitHead equals the immutable release target`,
  };
}

function wait(milliseconds) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, milliseconds);
}

export function readNpmVersionState(
  version,
  { attempts = 3, exec = execFileSync } = {},
) {
  let lastError = "";
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const output = exec(
        "npm",
        ["view", `${PACKAGE_NAME}@${version}`, "version", "gitHead", "--json"],
        {
          encoding: "utf8",
          stdio: ["ignore", "pipe", "pipe"],
        },
      );
      const payload = JSON.parse(String(output || "{}").trim() || "{}");
      if (typeof payload === "string") {
        return { exists: true, version: payload, gitHead: "" };
      }
      return {
        exists: true,
        version: clean(payload.version) || version,
        gitHead: clean(payload.gitHead),
      };
    } catch (error) {
      const details = `${String(error?.stdout || "")}\n${String(error?.stderr || "")}\n${String(error?.message || error)}`;
      if (/E404|404 Not Found|No match found|is not in this registry/i.test(details)) {
        return { exists: false, version, gitHead: "" };
      }
      lastError = details.replace(/\s+/g, " ").slice(0, 800);
      if (attempt < attempts) wait(attempt * 1000);
    }
  }
  throw new Error(
    `failed to determine whether ${PACKAGE_NAME}@${version} exists after ${attempts} attempts: ${lastError}`,
  );
}

function manualResult(env) {
  return {
    ok: true,
    inspect: false,
    eligible: true,
    reason: "manual workflow dispatch",
    version: clean(env.INPUT_VERSION),
    target_ref: clean(env.INPUT_TARGET_REF) || "main",
    dry_run: clean(env.INPUT_DRY_RUN) || "true",
    create_draft_release: clean(env.INPUT_CREATE_DRAFT_RELEASE) || "true",
    recover_existing_release:
      clean(env.INPUT_RECOVER_EXISTING_RELEASE) || "false",
    fault_case: clean(env.INPUT_FAULT_CASE) || "none",
    publish_confirmation: clean(env.INPUT_PUBLISH_CONFIRMATION),
    release_source_mode: "manual_dispatch",
    npm_version_exists: false,
    npm_git_head: "",
    recovery_required: false,
  };
}

function automaticResult(env, root) {
  const recoveryAuthorized = automaticRecoveryRequested(env.RUN_ATTEMPT);
  const event = inspectMainPushEvent({
    eventName: env.EVENT_NAME,
    repository: env.GITHUB_REPOSITORY,
    ref: env.PUSH_REF,
    beforeSha: env.PUSH_BEFORE_SHA,
    afterSha: env.PUSH_AFTER_SHA,
  });
  if (!event.ok || !event.inspect) {
    return {
      ...event,
      eligible: false,
      version: "",
      target_ref: "",
      dry_run: "false",
      create_draft_release: "true",
      recover_existing_release: recoveryAuthorized ? "true" : "false",
      fault_case: "none",
      publish_confirmation: "",
      release_source_mode: "trusted_main_push",
      npm_version_exists: false,
      npm_git_head: "",
      recovery_required: false,
    };
  }
  const result = validateAutomaticRelease({
    eventName: env.EVENT_NAME,
    repository: env.GITHUB_REPOSITORY,
    ref: env.PUSH_REF,
    beforeSha: env.PUSH_BEFORE_SHA,
    afterSha: env.PUSH_AFTER_SHA,
    previousVersions: versionsFromGitRef(env.PUSH_BEFORE_SHA, root),
    currentVersions: versionsFromGitRef(env.PUSH_AFTER_SHA, root),
    changedFiles: changedFilesFromGitRange(
      env.PUSH_BEFORE_SHA,
      env.PUSH_AFTER_SHA,
      root,
    ),
  });
  if (!result.ok || !result.eligible) {
    return {
      ...result,
      version: result.version || "",
      target_ref: result.target_sha || "",
      dry_run: "false",
      create_draft_release: "true",
      recover_existing_release: recoveryAuthorized ? "true" : "false",
      fault_case: "none",
      publish_confirmation: "",
      release_source_mode: "trusted_main_push",
      npm_version_exists: false,
      npm_git_head: "",
      recovery_required: false,
    };
  }
  const guarded = applyNpmRegistryGuard({
    result,
    npmState: readNpmVersionState(result.version),
    recoveryAuthorized,
  });
  return {
    ...guarded,
    target_ref: guarded.target_sha,
    dry_run: "false",
    create_draft_release: "true",
    recover_existing_release: recoveryAuthorized ? "true" : "false",
    fault_case: "none",
    publish_confirmation: "",
    release_source_mode: "trusted_main_push",
  };
}

function outputValue(value) {
  return clean(value).replaceAll("\n", " ");
}

function writeOutputs(result, outputFile) {
  if (!outputFile) return;
  appendFileSync(
    outputFile,
    [
      `eligible=${result.eligible === true}`,
      `reason=${outputValue(result.reason)}`,
      `previous_version=${outputValue(result.previous_version)}`,
      `version=${outputValue(result.version)}`,
      `target_ref=${outputValue(result.target_ref)}`,
      `dry_run=${outputValue(result.dry_run)}`,
      `create_draft_release=${outputValue(result.create_draft_release)}`,
      `recover_existing_release=${outputValue(result.recover_existing_release)}`,
      `fault_case=${outputValue(result.fault_case)}`,
      `publish_confirmation=${outputValue(result.publish_confirmation)}`,
      `release_source_mode=${outputValue(result.release_source_mode)}`,
      `npm_version_exists=${result.npm_version_exists === true}`,
      `npm_git_head=${outputValue(result.npm_git_head)}`,
      `recovery_required=${result.recovery_required === true}`,
      "",
    ].join("\n"),
    "utf8",
  );
}

function writeSummary(result, summaryFile) {
  if (!summaryFile) return;
  appendFileSync(
    summaryFile,
    [
      "## MemOS CLI release trigger",
      "",
      `- eligible: \`${result.eligible === true}\``,
      `- version transition: \`${result.previous_version || "unchanged"} -> ${result.version || "unchanged"}\``,
      `- npm version exists: \`${result.npm_version_exists === true}\``,
      `- recovery required: \`${result.recovery_required === true}\``,
      `- result: ${outputValue(result.reason)}`,
      "",
    ].join("\n"),
    "utf8",
  );
}

export function main(env = process.env) {
  if (!clean(env.GITHUB_OUTPUT)) throw new Error("GITHUB_OUTPUT is required");
  const result =
    env.EVENT_NAME === "workflow_dispatch"
      ? (() => {
          const manual = manualResult(env);
          return String(manual.dry_run) === "true"
            ? manual
            : applyManualNpmRecoveryGuard({
                result: manual,
                npmState: readNpmVersionState(manual.version),
              });
        })()
      : automaticResult(env, env.GITHUB_WORKSPACE || process.cwd());
  writeOutputs(result, env.GITHUB_OUTPUT);
  writeSummary(result, env.GITHUB_STEP_SUMMARY);
  if (!result.ok) throw new Error(result.reason);
  console.log(
    result.eligible
      ? `CLI release accepted: version=${result.version}, target=${result.target_ref}, source=${result.release_source_mode}`
      : `CLI release skipped: ${result.reason}`,
  );
  return result;
}

const isDirectRun =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isDirectRun) {
  try {
    main();
  } catch (error) {
    console.error(`::error::${error?.message || String(error)}`);
    process.exitCode = 1;
  }
}
