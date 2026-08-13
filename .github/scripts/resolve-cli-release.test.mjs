import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";

import {
  VERSION_FILES,
  applyManualNpmRecoveryGuard,
  applyNpmRegistryGuard,
  automaticRecoveryRequested,
  changedFilesFromGitRange,
  inspectPullRequestEvent,
  inspectVersionTransition,
  validateAutomaticRelease,
  versionsFromGitRef,
} from "./resolve-cli-release.mjs";

const REPOSITORY = "MemTensor/MemOS-Cloud-CLI";
const MERGE_SHA = "a".repeat(40);
const BASE_SHA = "b".repeat(40);

function versions(version) {
  return Object.fromEntries(VERSION_FILES.map((file) => [file, version]));
}

function valid(overrides = {}) {
  return {
    eventName: "pull_request",
    merged: "true",
    baseRef: "main",
    headRepo: REPOSITORY,
    repository: REPOSITORY,
    mergeSha: MERGE_SHA,
    baseSha: BASE_SHA,
    previousVersions: versions("1.0.6"),
    currentVersions: versions("1.0.7"),
    changedFiles: [...VERSION_FILES],
    ...overrides,
  };
}

function git(root, args) {
  return execFileSync("git", args, {
    cwd: root,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function write(root, file, contents) {
  const path = join(root, file);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, contents, "utf8");
}

function writeVersions(root, version) {
  write(
    root,
    "package.json",
    `${JSON.stringify({ name: "@memtensor/memos-cloud-cli", version }, null, 2)}\n`,
  );
  write(
    root,
    "pyproject.toml",
    `[project]\nname = "memos-cli"\nversion = "${version}"\n`,
  );
  write(
    root,
    "src/memos_cli/__init__.py",
    `\"\"\"MemOS CLI.\"\"\"\n\n__version__ = "${version}"\n`,
  );
}

function commit(root, message) {
  git(root, ["add", "."]);
  git(root, ["commit", "-q", "-m", message]);
  return git(root, ["rev-parse", "HEAD"]);
}

test("accepts a same-repository main merge when all three versions increase", () => {
  const result = validateAutomaticRelease(valid());
  assert.equal(result.ok, true);
  assert.equal(result.eligible, true);
  assert.equal(result.previous_version, "1.0.6");
  assert.equal(result.version, "1.0.7");
  assert.equal(result.target_sha, MERGE_SHA);
  assert.deepEqual(result.changed_version_files, VERSION_FILES);
});

test("does not rely on a release branch name", () => {
  const result = validateAutomaticRelease(valid());
  assert.equal(result.eligible, true);
  assert.equal("headRef" in result, false);
});

test("only an explicit automatic workflow rerun authorizes orphan-tag recovery", () => {
  assert.equal(automaticRecoveryRequested("1"), false);
  assert.equal(automaticRecoveryRequested("2"), true);
  assert.equal(automaticRecoveryRequested("12"), true);
  assert.equal(automaticRecoveryRequested("invalid"), false);
});

test("ordinary merged PRs with unchanged versions succeed and skip release", () => {
  const result = validateAutomaticRelease(
    valid({ currentVersions: versions("1.0.6"), changedFiles: [] }),
  );
  assert.equal(result.ok, true);
  assert.equal(result.eligible, false);
  assert.match(result.reason, /did not change/);
});

test("fork, unmerged, and non-main PR events are ignored", () => {
  for (const input of [
    valid({ merged: "false" }),
    valid({ headRepo: "someone/fork" }),
    valid({ baseRef: "test" }),
  ]) {
    const result = inspectPullRequestEvent(input);
    assert.equal(result.ok, true);
    assert.equal(result.inspect, false);
  }
});

test("fails closed when a version bump omits any of the three version files", () => {
  const current = versions("1.0.6");
  current["package.json"] = "1.0.7";
  const result = inspectVersionTransition({
    previousVersions: versions("1.0.6"),
    currentVersions: current,
    changedFiles: ["package.json"],
  });
  assert.equal(result.ok, false);
  assert.equal(result.eligible, false);
  assert.match(result.reason, /all three version files were not updated/);
});

test("fails closed when merged versions disagree", () => {
  const current = versions("1.0.7");
  current["src/memos_cli/__init__.py"] = "1.0.8";
  const result = validateAutomaticRelease(
    valid({ currentVersions: current }),
  );
  assert.equal(result.ok, false);
  assert.match(result.reason, /inconsistent versions/);
});

test("rejects invalid SemVer, downgrade, equal precedence, and build metadata", () => {
  for (const [previous, current, pattern] of [
    ["1.0.6", "1.0.07", /strict SemVer/],
    ["1.0.7", "1.0.6", /must increase/],
    ["1.0.7", "1.0.7-beta.1", /must increase/],
    ["1.0.7+one", "1.0.7+two", /build metadata/],
  ]) {
    const result = inspectVersionTransition({
      previousVersions: versions(previous),
      currentVersions: versions(current),
      changedFiles: [...VERSION_FILES],
    });
    assert.equal(result.ok, false);
    assert.match(result.reason, pattern);
  }
});

test("accepts beta increments and beta-to-stable promotion", () => {
  for (const [previous, current] of [
    ["1.0.7-beta.1", "1.0.7-beta.2"],
    ["1.0.7-beta.2", "1.0.7"],
  ]) {
    const result = inspectVersionTransition({
      previousVersions: versions(previous),
      currentVersions: versions(current),
      changedFiles: [...VERSION_FILES],
    });
    assert.equal(result.ok, true);
    assert.equal(result.eligible, true);
  }
});

test("requires immutable base and merge SHAs", () => {
  for (const input of [
    valid({ mergeSha: "abc123" }),
    valid({ baseSha: "abc123" }),
  ]) {
    const result = validateAutomaticRelease(input);
    assert.equal(result.ok, false);
    assert.match(result.reason, /40-character/);
  }
});

test("npm absence allows a new Draft while npm presence requires manual recovery", () => {
  const eligible = validateAutomaticRelease(valid());
  const fresh = applyNpmRegistryGuard({
    result: eligible,
    npmState: { exists: false },
  });
  assert.equal(fresh.ok, true);
  assert.equal(fresh.eligible, true);
  assert.equal(fresh.recovery_required, false);

  const existing = applyNpmRegistryGuard({
    result: eligible,
    npmState: { exists: true, gitHead: MERGE_SHA },
  });
  assert.equal(existing.ok, false);
  assert.equal(existing.eligible, false);
  assert.equal(existing.recovery_required, true);
  assert.match(existing.reason, /manual recovery input/);

  const recovered = applyNpmRegistryGuard({
    result: eligible,
    npmState: { exists: true, gitHead: MERGE_SHA },
    recoveryAuthorized: true,
  });
  assert.equal(recovered.ok, true);
  assert.equal(recovered.eligible, true);
  assert.equal(recovered.recovery_required, true);
  assert.match(recovered.reason, /explicit workflow rerun/);

  const conflict = applyNpmRegistryGuard({
    result: eligible,
    npmState: { exists: true, gitHead: "c".repeat(40) },
  });
  assert.equal(conflict.ok, false);
  assert.match(conflict.reason, /not the reviewed merge commit/);
});

test("manual real runs require explicit recovery when npm already has the version", () => {
  const manual = {
    ok: true,
    eligible: true,
    reason: "manual workflow dispatch",
    version: "1.0.7",
    target_ref: "main",
    dry_run: "false",
    recover_existing_release: "false",
  };
  const blocked = applyManualNpmRecoveryGuard({
    result: manual,
    npmState: { exists: true, gitHead: MERGE_SHA },
  });
  assert.equal(blocked.ok, false);
  assert.equal(blocked.recovery_required, true);
  assert.match(blocked.reason, /explicitly enable recover_existing_release/);

  const allowed = applyManualNpmRecoveryGuard({
    result: { ...manual, recover_existing_release: "true" },
    npmState: { exists: true, gitHead: MERGE_SHA },
  });
  assert.equal(allowed.ok, true);
  assert.equal(allowed.eligible, true);
  assert.equal(allowed.npm_git_head, MERGE_SHA);

  const untrusted = applyManualNpmRecoveryGuard({
    result: { ...manual, recover_existing_release: "true" },
    npmState: { exists: true, gitHead: "unknown" },
  });
  assert.equal(untrusted.ok, false);
  assert.match(untrusted.reason, /no trustworthy 40-character npm gitHead/);
});

test("reads all three version formats and their actual PR diff from immutable refs", () => {
  const root = mkdtempSync(join(tmpdir(), "memos-cli-auto-release-"));
  git(root, ["init", "-q"]);
  git(root, ["config", "user.email", "release-test@example.invalid"]);
  git(root, ["config", "user.name", "Release Test"]);
  writeVersions(root, "1.0.6");
  const base = commit(root, "chore: baseline");
  writeVersions(root, "1.0.7");
  const target = commit(root, "release: update CLI version");

  assert.deepEqual(versionsFromGitRef(base, root), versions("1.0.6"));
  assert.deepEqual(versionsFromGitRef(target, root), versions("1.0.7"));
  assert.deepEqual(
    changedFilesFromGitRange(base, target, root).sort(),
    [...VERSION_FILES].sort(),
  );
});
