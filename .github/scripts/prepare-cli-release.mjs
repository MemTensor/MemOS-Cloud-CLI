#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

export const PRODUCT_ID = "memos-cloud-cli";
export const PRODUCT_TITLE = { zh: "MemOS CLI", en: "MemOS CLI" };
export const RELEASE_CATEGORIES = ["Added", "Improved", "Fixed"];
export const DOCS_CATEGORIES = {
  Added: "New Features",
  Improved: "Improvements",
  Fixed: "Bug Fixes",
};
export const MAX_DRAFT_ATTEMPTS = 3;
export const MAX_RELEASE_ITEMS = 12;
export const MAX_TEXT_CN_CHARS = 180;
export const MAX_TEXT_EN_CHARS = 220;
export const RELEASE_FAULT_CASES = [
  "none",
  "mixed_language",
  "missing_source_refs",
  "invalid_source_ref",
  "missing_important_commit",
  "thirteen_items",
  "too_long",
];
export const RELEASE_SOURCE_MODES = [
  "manual_dispatch",
  "trusted_main_push",
];
export const RELEASE_NOTE_METHODS = [
  {
    source: "reviewed-release-notes-file",
    url: "https://github.com/MemTensor/memmy-agent/tree/main/.github/release-notes",
    applied_as:
      "Prefer an optional .github/release-notes/vX.Y.Z.md reviewed in the release PR; otherwise use the validated Doc Agent draft.",
  },
  {
    source: "github-auto-generated-release-notes",
    url: "https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes",
    applied_as:
      "Append GitHub-generated whole-repository What's Changed notes for a complete auditable change list.",
  },
  {
    source: "keep-a-changelog",
    url: "https://keepachangelog.com/en/1.1.0/",
    applied_as:
      "Group the shorter Plugin tab copy by Added, Improved, and Fixed.",
  },
  {
    source: "conventional-commits",
    url: "https://www.conventionalcommits.org/en/v1.0.0/",
    applied_as:
      "Use commit types as evidence hints, never as final user-facing copy.",
  },
];

const CJK_RE = /[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]/;
const CORE_NUMBER_RE = /^(0|[1-9]\d*)$/;
const NUMERIC_IDENTIFIER_RE = /^\d+$/;
const PRIVATE_KEY_RE =
  /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g;
const AWS_ACCESS_KEY_RE = /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g;
const JWT_RE =
  /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g;
const TOKEN_RE =
  /(github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+|npm_[A-Za-z0-9_]+|xox[baprs]-[A-Za-z0-9-]+|Bearer\s+[A-Za-z0-9._~+/=-]+)/gi;
const PRIVATE_URL_RE =
  /https?:\/\/(?:(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|localhost(?::\d+)?|[^/\s"'<>)]*\.(?:internal|local)(?::\d+)?)[^\s"'<>)]*/gi;
const PRIVATE_IP_RE =
  /\b(?:(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?::\d+)?\b/g;
const INTERNAL_HOST_RE = /\b[A-Za-z0-9.-]+\.(?:internal|local)(?::\d+)?\b/gi;
const AUTH_HEADER_RE =
  /\b(Authorization\s*:\s*)(?:Basic|Bearer)\s+[A-Za-z0-9._~+/=-]{8,}/gi;
const SECRET_ASSIGNMENT_RE =
  /\b((?:api[_-]?key|access[_-]?key(?:[_-]?(?:id|secret))?|secret(?:[_-]?key)?|client[_-]?secret|password|passwd|token|signature|service_id)\s*[:=]\s*)["']?[^"'\s&),;]+/gi;

function fail(message) {
  throw new Error(String(message));
}

function warn(message) {
  console.error(`::warning::${sanitizeError(message)}`);
}

function sh(args, options = {}) {
  return execFileSync("git", args, {
    cwd: process.cwd(),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  }).trim();
}

function tryGit(args) {
  try {
    return sh(args);
  } catch {
    return "";
  }
}

function gitSucceeds(args) {
  try {
    sh(args);
    return true;
  } catch {
    return false;
  }
}

function lines(value) {
  return String(value || "")
    .split("\n")
    .map((line) => line.trimEnd())
    .filter(Boolean);
}

export function redact(value) {
  return String(value ?? "")
    .replace(PRIVATE_KEY_RE, "[REDACTED_PRIVATE_KEY]")
    .replace(AUTH_HEADER_RE, "$1[REDACTED_AUTH]")
    .replace(TOKEN_RE, "[REDACTED_TOKEN]")
    .replace(AWS_ACCESS_KEY_RE, "[REDACTED_TOKEN]")
    .replace(JWT_RE, "[REDACTED_TOKEN]")
    .replace(PRIVATE_URL_RE, "[REDACTED_INTERNAL_URL]")
    .replace(
      /https?:\/\/[^\s"'<>)]*\/internal(?:\/[^\s"'<>)]*)?/gi,
      "[REDACTED_INTERNAL_URL]",
    )
    .replace(INTERNAL_HOST_RE, "[REDACTED_INTERNAL_HOST]")
    .replace(
      /([?&](?:token|access_token|secret|signature|service_id)=)[^&\s"')]+/gi,
      "$1[REDACTED]",
    )
    .replace(SECRET_ASSIGNMENT_RE, "$1[REDACTED]")
    .replace(PRIVATE_IP_RE, "[REDACTED_IP]");
}

export function hasSensitiveContent(value) {
  const original = String(value ?? "");
  return redact(original) !== original;
}

function assertNoSensitiveContent(value, label) {
  if (hasSensitiveContent(value)) {
    fail(
      `${label} contains credential-like or internal content; redact the source data before release.`,
    );
  }
}

export function sanitizeError(value) {
  return redact(value)
    .replace(/https?:\/\/[^\s"'<>)]*/gi, "[REDACTED_URL]")
    .replace(/\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b/g, "[REDACTED_IP]")
    .replace(/\s+/g, " ")
    .slice(0, 1000);
}

export function cleanVersion(raw) {
  const value = String(raw || "").trim();
  if (!value) fail("version is required.");
  if (value.startsWith("v")) fail("version must not include a leading v.");
  if (!parseSemver(value)) {
    fail(`version must be valid SemVer, received: ${value}`);
  }
  return value;
}

export function parseSemver(raw) {
  const value = String(raw || "").trim().replace(/^v/, "");
  const match = value.match(
    /^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$/,
  );
  if (!match) return null;
  if (![match[1], match[2], match[3]].every((part) => CORE_NUMBER_RE.test(part))) {
    return null;
  }
  const prerelease = match[4] ? match[4].split(".") : [];
  if (
    prerelease.some(
      (identifier) =>
        NUMERIC_IDENTIFIER_RE.test(identifier) &&
        !CORE_NUMBER_RE.test(identifier),
    )
  ) {
    return null;
  }
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
    prerelease,
  };
}

function compareIdentifier(left, right) {
  const leftNumeric = NUMERIC_IDENTIFIER_RE.test(left);
  const rightNumeric = NUMERIC_IDENTIFIER_RE.test(right);
  if (leftNumeric && rightNumeric) {
    const a = BigInt(left);
    const b = BigInt(right);
    if (a > b) return 1;
    if (a < b) return -1;
    return 0;
  }
  if (leftNumeric) return -1;
  if (rightNumeric) return 1;
  return left.localeCompare(right);
}

export function compareSemver(left, right) {
  const a = parseSemver(left);
  const b = parseSemver(right);
  if (!a || !b) return String(left).localeCompare(String(right));
  for (const field of ["major", "minor", "patch"]) {
    if (a[field] !== b[field]) return a[field] - b[field];
  }
  if (!a.prerelease.length && !b.prerelease.length) return 0;
  if (!a.prerelease.length) return 1;
  if (!b.prerelease.length) return -1;
  const length = Math.max(a.prerelease.length, b.prerelease.length);
  for (let index = 0; index < length; index += 1) {
    if (a.prerelease[index] === undefined) return -1;
    if (b.prerelease[index] === undefined) return 1;
    const result = compareIdentifier(a.prerelease[index], b.prerelease[index]);
    if (result !== 0) return result;
  }
  return 0;
}

export function findPreviousTag(version, currentTag, tags) {
  const target = cleanVersion(version);
  const parsedTarget = parseSemver(target);
  const stableTarget = parsedTarget.prerelease.length === 0;
  return tags
    .map((tag) => String(tag || "").trim())
    .filter((tag) => tag !== currentTag && /^v\d+\.\d+\.\d+/.test(tag))
    .map((tag) => ({ tag, parsed: parseSemver(tag) }))
    .filter((item) => item.parsed)
    .filter((item) => !stableTarget || item.parsed.prerelease.length === 0)
    .filter((item) => compareSemver(item.tag, target) < 0)
    .sort((a, b) => compareSemver(b.tag, a.tag))[0]?.tag || "";
}

export function validateReleaseVersionOrder(version, currentTag, tags) {
  const target = cleanVersion(version);
  const latest = tags
    .map((tag) => String(tag || "").trim())
    .filter((tag) => tag && tag !== currentTag && parseSemver(tag))
    .sort((left, right) => compareSemver(right, left))[0];
  if (latest && compareSemver(target, latest) <= 0) {
    fail(
      `${currentTag} must be newer than the latest existing SemVer tag ${latest}; refusing an out-of-order release.`,
    );
  }
  return latest || "";
}

export function validateReleaseSourceMode(raw) {
  const value = String(raw || "manual_dispatch").trim() || "manual_dispatch";
  if (!RELEASE_SOURCE_MODES.includes(value)) {
    fail(`unknown release source mode: ${value}`);
  }
  return value;
}

export function validatePublishConfirmation({
  dryRun,
  version,
  confirmation,
  releaseSourceMode = "manual_dispatch",
}) {
  if (String(dryRun) === "true") return;
  if (validateReleaseSourceMode(releaseSourceMode) === "trusted_main_push") {
    return;
  }
  const expected = `PUBLISH v${cleanVersion(version)}`;
  if (String(confirmation || "").trim() !== expected) {
    fail(`dry_run=false requires publish_confirmation to exactly equal: ${expected}`);
  }
}

export function validateDraftFirstRelease({
  dryRun,
  createDraftRelease,
}) {
  if (String(dryRun) === "true") return;
  if (String(createDraftRelease).toLowerCase() !== "true") {
    fail(
      "dry_run=false requires create_draft_release=true so a release owner can review the Draft Release before release.published.",
    );
  }
}

export function validateReleaseTarget({
  dryRun,
  targetRef,
  releaseSourceMode = "manual_dispatch",
}) {
  if (String(dryRun) === "true") return;
  if (validateReleaseSourceMode(releaseSourceMode) === "trusted_main_push") {
    if (!/^[0-9a-f]{40}$/i.test(String(targetRef || "").trim())) {
      fail("trusted main push target must be its 40-character after commit SHA.");
    }
    return;
  }
  if (String(targetRef || "main").trim() !== "main") {
    fail("dry_run=false requires target_ref to be exactly main.");
  }
}

export function validateLiveReleaseSource({
  dryRun,
  workflowRef,
  defaultBranch = "main",
  targetSha,
  defaultBranchSha,
  targetIsDefaultBranchAncestor = false,
  releaseSourceMode = "manual_dispatch",
}) {
  const branch = String(defaultBranch || "main").trim() || "main";
  const sourceMode = validateReleaseSourceMode(releaseSourceMode);
  if (sourceMode === "trusted_main_push") {
    if (!targetIsDefaultBranchAncestor) {
      fail(
        `trusted main push target must be contained in origin/${branch}; refusing a commit outside the protected default branch.`,
      );
    }
    return;
  }
  if (
    String(workflowRef || "").trim() &&
    String(workflowRef).trim() !== `refs/heads/${branch}`
  ) {
    fail(
      `release inspection must be dispatched from the protected default branch ${branch}; use target_ref to inspect another branch or commit.`,
    );
  }
  if (String(dryRun) === "true") return;
  if (
    String(defaultBranchSha || "").trim() &&
    String(targetSha || "").trim() !== String(defaultBranchSha).trim()
  ) {
    fail(
      `dry_run=false target must equal origin/${branch}; refusing a stale or non-default commit.`,
    );
  }
}

export function validateDocAgentConfiguration({
  allowOffline = false,
  env = process.env,
} = {}) {
  if (allowOffline) return;
  const required = [
    "DOC_AGENT_RELEASE_NOTES_DRAFT_URL",
    "DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN",
    "DOC_AGENT_RELEASE_FAILURE_URL",
  ];
  const missing = required.filter(
    (name) => !String(env[name] || "").trim(),
  );
  if (missing.length) {
    fail(`missing required Actions secrets: ${missing.join(", ")}`);
  }
  const parsedUrls = {};
  for (const name of [
    "DOC_AGENT_RELEASE_NOTES_DRAFT_URL",
    "DOC_AGENT_RELEASE_FAILURE_URL",
  ]) {
    let parsed;
    try {
      parsed = new URL(String(env[name]).trim());
    } catch {
      fail(`${name} must be a valid HTTP(S) URL.`);
    }
    if (!/^https?:$/.test(parsed.protocol)) {
      fail(`${name} must be a valid HTTP(S) URL.`);
    }
    parsedUrls[name] = parsed;
  }
  if (
    parsedUrls.DOC_AGENT_RELEASE_NOTES_DRAFT_URL.origin !==
    parsedUrls.DOC_AGENT_RELEASE_FAILURE_URL.origin
  ) {
    fail(
      "DOC_AGENT_RELEASE_FAILURE_URL must use the same origin as DOC_AGENT_RELEASE_NOTES_DRAFT_URL when sharing the draft token.",
    );
  }
}

export function validateFaultCase({ dryRun, faultCase }) {
  const value = String(faultCase || "none").trim() || "none";
  if (!RELEASE_FAULT_CASES.includes(value)) {
    fail(`unknown release fault case: ${value}`);
  }
  if (String(dryRun) !== "true" && value !== "none") {
    fail("release fault injection is only allowed when dry_run=true.");
  }
  return value;
}

export function sourceRefsFromText(text) {
  const refs = new Set();
  const pattern =
    /\(#(\d+)\)|\b(?:PR|Fix(?:es)?|Close[sd]?|Refs?|Issue|in)\s+#(\d+)|\/(?:pull|issues)\/(\d+)\b/gi;
  for (const match of String(text || "").matchAll(pattern)) {
    refs.add(`#${match[1] || match[2] || match[3]}`);
  }
  return [...refs];
}

function resolveRef(raw) {
  const value = String(raw || "main").trim() || "main";
  for (const candidate of [
    value,
    value.startsWith("origin/") ? "" : `origin/${value}`,
  ].filter(Boolean)) {
    const sha = tryGit(["rev-parse", "--verify", `${candidate}^{commit}`]);
    if (sha) return { ref: candidate, sha };
  }
  fail(`cannot resolve target_ref to a commit: ${value}`);
}

function versionSources(ref) {
  const packageText = tryGit(["show", `${ref}:package.json`]);
  const pyprojectText = tryGit(["show", `${ref}:pyproject.toml`]);
  const initText = tryGit(["show", `${ref}:src/memos_cli/__init__.py`]);
  let packageVersion = "";
  try {
    packageVersion = JSON.parse(packageText).version || "";
  } catch {
    fail(`cannot parse package.json at ${ref}`);
  }
  return {
    package_json: packageVersion,
    pyproject_toml:
      pyprojectText.match(/^version\s*=\s*"([^"]+)"/m)?.[1] || "",
    python_init:
      initText.match(/^__version__\s*=\s*"([^"]+)"/m)?.[1] || "",
  };
}

export function validateVersionSources(version, sources) {
  const mismatches = Object.entries(sources).filter(
    ([, value]) => String(value || "") !== version,
  );
  if (mismatches.length) {
    fail(
      `target_ref version files must all equal ${version}: ${mismatches
        .map(([name, value]) => `${name}=${value || "<missing>"}`)
        .join(", ")}`,
    );
  }
}

function commitBody(sha) {
  return redact(tryGit(["show", "--no-patch", "--format=%B", sha])).slice(
    0,
    24000,
  );
}

function touchedFilesForCommit(sha) {
  return lines(
    tryGit([
      "diff-tree",
      "--root",
      "--no-commit-id",
      "--name-only",
      "-r",
      sha,
    ]),
  );
}

function refsForCommit(commit) {
  return [
    ...new Set([
      commit.short_sha,
      commit.sha,
      ...sourceRefsFromText(`${commit.subject}\n${commit.body_excerpt}`),
    ]),
  ].filter(Boolean);
}

function revertedCommitShas(commits) {
  const reverted = new Set();
  for (const commit of commits) {
    if (!/^revert\b/i.test(commit.subject)) continue;
    const match = commit.body_excerpt.match(
      /This reverts commit ([0-9a-f]{7,40})\b/i,
    );
    if (match) reverted.add(match[1].toLowerCase());
  }
  return reverted;
}

function isReverted(commit, reverted) {
  return [...reverted].some(
    (sha) =>
      commit.sha.toLowerCase().startsWith(sha) ||
      sha.startsWith(commit.short_sha.toLowerCase()),
  );
}

function isImportantCommit(commit, reverted) {
  const subject = String(commit.subject || "").trim();
  if (!subject || isReverted(commit, reverted)) return false;
  if (/^merge\b/i.test(subject)) return false;
  if (commit.touched_files.length === 0) return false;
  if (/^(ci|chore|docs|test|style|build)(\([^)]+\))?:/i.test(subject)) {
    return false;
  }
  if (
    /^(?:feat|fix|perf|refactor)\((?:ci|build|release|workflow|test|tests|docs|chore|deps)\)!?:/i.test(
      subject,
    )
  ) {
    return false;
  }
  if (
    /(?:bump|update|modify|prepare|修改|更新|调整).{0,24}(?:version|版本号)/i.test(
      subject,
    )
  ) {
    return false;
  }
  if (/\b(?:workflow|release automation|build venv)\b/i.test(subject)) {
    return false;
  }
  if (
    commit.touched_files.length > 0 &&
    commit.touched_files.every(
      (path) =>
        path.startsWith(".github/") ||
        /(^|\/)(?:tests?|__tests__)\//.test(path) ||
        /(^|\/)docs?\//.test(path) ||
        /\.(?:test|spec)\.[^.]+$/i.test(path),
    )
  ) {
    return false;
  }
  if (/^revert\b/i.test(subject)) return true;
  return /^(feat|fix|perf|refactor)(\([^)]+\))?!?:|^(add|fix|improv|optimi[sz]|support|allow|prevent|resolve|correct|stabili[sz]|compat)\b|新增|修复|优化|增强|支持|兼容|改进|纠正|避免/i.test(subject);
}

function changedFiles(range) {
  const statusByPath = new Map();
  for (const line of lines(
    tryGit(["diff", "--name-status", "--find-renames", range]),
  )) {
    const fields = line.split("\t");
    const path = fields.at(-1);
    statusByPath.set(path, {
      status: fields[0],
      path,
      ...(fields.length === 3 ? { old_path: fields[1] } : {}),
    });
  }
  const stats = new Map();
  for (const line of lines(tryGit(["diff", "--numstat", range]))) {
    const [additions, deletions, path] = line.split("\t");
    stats.set(path, {
      additions: additions === "-" ? null : Number(additions),
      deletions: deletions === "-" ? null : Number(deletions),
    });
  }
  return [...statusByPath.values()].map((item) => ({
    ...item,
    ...(stats.get(item.path) || {}),
  }));
}

function patchSnippets(range, files) {
  const interesting = files
    .map((item) => item.path)
    .filter(
      (path) =>
        !path.startsWith(".github/") &&
        !/(^|\/)(tests?|__tests__)\//.test(path) &&
        /\.(py|js|mjs|json|toml|md|yaml|yml|sh|ps1)$/i.test(path),
    )
    .slice(0, 12);
  const snippets = [];
  let total = 0;
  for (const path of interesting) {
    if (total >= 16000) break;
    const raw = tryGit([
      "diff",
      "--unified=1",
      "--no-ext-diff",
      range,
      "--",
      path,
    ]);
    if (!raw) continue;
    const patch = redact(raw).slice(0, 5000);
    total += patch.length;
    snippets.push({ path, patch, truncated: raw.length > patch.length });
  }
  return snippets;
}

function packageChanges(previousTag, currentRef) {
  const before = versionSources(previousTag);
  const after = versionSources(currentRef);
  return Object.keys(after)
    .filter((field) => before[field] !== after[field])
    .map((field) => ({ field, before: before[field], after: after[field] }));
}

export function collectCliEvidence({
  previousTag,
  currentTag,
  currentRef,
  targetVersion,
  repo,
}) {
  const range = `${previousTag}..${currentRef}`;
  const records = tryGit([
    "log",
    "--format=%H%x1f%h%x1f%an%x1f%aI%x1f%s%x1e",
    range,
  ])
    .split("\x1e")
    .map((record) => record.trim())
    .filter(Boolean);
  const commits = records.map((record) => {
    const [sha = "", shortSha = "", author = "", date = "", subject = ""] =
      record.split("\x1f");
    const commit = {
      sha,
      short_sha: shortSha,
      author: redact(author),
      date,
      subject: redact(subject),
      body_excerpt: commitBody(sha),
      touched_files: touchedFilesForCommit(sha),
    };
    return { ...commit, source_refs: refsForCommit(commit) };
  });
  const files = changedFiles(range);
  const reverted = revertedCommitShas(commits);
  const finalPaths = new Set(
    files.flatMap((item) => [item.path, item.old_path].filter(Boolean)),
  );
  const important = commits
    .filter((commit) => isImportantCommit(commit, reverted))
    .filter((commit) =>
      commit.touched_files.some((path) => finalPaths.has(path)),
    );
  const prNumbers = new Set(
    commits.flatMap((commit) =>
      commit.source_refs
        .filter((ref) => ref.startsWith("#"))
        .map((ref) => ref.slice(1)),
    ),
  );
  return {
    product_id: PRODUCT_ID,
    product_title: PRODUCT_TITLE,
    repo,
    release_repo: repo,
    previous_tag: previousTag,
    current_tag: currentTag,
    target_version: currentTag,
    git_ref: currentRef,
    evidence_scope: "whole_repository",
    product_paths: ["**"],
    has_product_changes: files.length > 0,
    has_user_facing_product_changes: important.length > 0,
    skip_reason: important.length
      ? ""
      : files.length
        ? "repository changed, but no user-facing feat/fix/perf/refactor evidence was found"
        : "no repository changes in the release range",
    commits,
    important_commits: important,
    reverted_commit_shas: [...reverted],
    required_source_refs: important.map((commit) => ({
      sha: commit.sha,
      short_sha: commit.short_sha,
      subject: commit.subject,
      accepted_refs: commit.source_refs,
    })),
    pull_requests: [...prNumbers]
      .sort((a, b) => Number(a) - Number(b))
      .map((number) => ({
        number,
        url: `https://github.com/${repo}/pull/${number}`,
      })),
    changed_files: files,
    diff_stat: {
      text: redact(tryGit(["diff", "--stat=200,200", range])),
      files: files.map(({ path, additions, deletions }) => ({
        path,
        additions,
        deletions,
      })),
    },
    important_diff: {
      whole_repository: patchSnippets(range, files),
    },
    package_changes: packageChanges(previousTag, currentRef),
    test_changes: files.filter(
      (item) =>
        /(^|\/)(test|tests|__tests__)\//.test(item.path) ||
        /\.test\./.test(item.path),
    ),
    docs_changes: files.filter((item) => /\.(md|mdx|rst)$/i.test(item.path)),
    release_note_quality_request: {
      candidate_count: 3,
      max_repair_attempts: MAX_DRAFT_ATTEMPTS,
      methodology: RELEASE_NOTE_METHODS,
      require_source_refs: true,
      require_bilingual_output: true,
      require_docs_preview: true,
      fail_closed: true,
      scoring: [
        "evidence coverage",
        "source_refs validity",
        "Chinese and English language purity",
        "Plugin tab readability",
      ],
      style_policy: [
        "Each bullet must name the concrete CLI behavior and explain its user-facing impact in one sentence.",
        "Avoid generic restatements such as '新增了 X 功能', '优化了 X 性能', or '修复了 X 问题'.",
        "Do not copy Conventional Commit prefixes or PR-number prose into user-facing text.",
      ],
      curation_policy: [
        "Summarize only user-visible MemOS CLI changes from the evidence.",
        "Do not present CI, packaging, release automation, or test-only work as product features.",
        "Group related commits into concise Added, Improved, or Fixed bullets.",
        "Preserve all covered source_refs when commits are grouped.",
        "Do not mention private endpoints, credentials, internal infrastructure, or raw build paths.",
      ],
    },
    target_surface: "memos_docs_plugin_changelog",
    release_context: {
      release_kind: "standalone_repository",
      public_release_body:
        "optional_reviewed_file_or_validated_doc_agent_draft_plus_github_whats_changed",
      docs_product_extraction: "whole_tag_range_after_release_published",
    },
    release_note_methodology: RELEASE_NOTE_METHODS,
  };
}

async function fetchJsonWithRetry(
  url,
  options,
  { label, attempts = 3 } = {},
) {
  const errors = [];
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetch(url, options);
      const text = await response.text();
      let payload = {};
      try {
        payload = text ? JSON.parse(text) : {};
      } catch {
        payload = { raw: text };
      }
      if (!response.ok) {
        const error = new Error(
          `HTTP ${response.status} ${JSON.stringify(payload).slice(0, 500)}`,
        );
        error.errorCode = `HTTP_${response.status}`;
        error.retryable =
          response.status === 408 ||
          response.status === 409 ||
          response.status === 425 ||
          response.status === 429 ||
          response.status >= 500;
        throw error;
      }
      return payload;
    } catch (error) {
      errors.push({
        error_code: error?.errorCode || "EXTERNAL_REQUEST",
        message: sanitizeError(error?.message || error),
        retryable: error?.retryable !== false,
      });
      if (error?.retryable === false) {
        const wrapped = new Error(
          `${label} failed without retry: ${errors.at(-1).message}`,
        );
        wrapped.attempts = errors;
        throw wrapped;
      }
      if (attempt === attempts) {
        const wrapped = new Error(
          `${label} failed after ${attempts} attempts: ${errors
            .map((item) => item.message)
            .join(" | ")}`,
        );
        wrapped.attempts = errors;
        throw wrapped;
      }
      const backoff = Math.min(4000, 400 * 2 ** (attempt - 1));
      const jitter = Math.floor(Math.random() * 200);
      await new Promise((resolve) => setTimeout(resolve, backoff + jitter));
    }
  }
  fail(`${label} failed.`);
}

function optionalHttpUrlFromEnv(name) {
  const value = String(process.env[name] || "").trim();
  if (!value) return "";
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    fail(`${name} must be a valid HTTP(S) URL.`);
  }
  if (!/^https?:$/.test(parsed.protocol)) {
    fail(`${name} must be a valid HTTP(S) URL.`);
  }
  const draftUrl = String(
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL || "",
  ).trim();
  if (draftUrl) {
    const draft = new URL(draftUrl);
    if (draft.origin !== parsed.origin) {
      fail(
        `${name} must use the same origin as DOC_AGENT_RELEASE_NOTES_DRAFT_URL when sharing the draft token.`,
      );
    }
  }
  return value;
}

export async function reportFailure(
  {
    evidence,
    attempts,
    finalError,
    phase = "release-notes",
  },
  { fetchImpl = fetch } = {},
) {
  if (!Array.isArray(attempts) || attempts.length < 3) {
    return { skipped: true, reason: "fewer than three exhausted attempts" };
  }
  const url = optionalHttpUrlFromEnv("DOC_AGENT_RELEASE_FAILURE_URL");
  const token = String(
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN || "",
  ).trim();
  if (!url) return { skipped: true, reason: "missing configured failure URL" };
  if (!token) return { skipped: true, reason: "missing configured token" };
  const runId = String(process.env.GITHUB_RUN_ID || "").trim();
  const response = await fetchImpl(url, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      product_id: PRODUCT_ID,
      repository: evidence.repo,
      version: evidence.target_version,
      phase,
      run_id: runId || `${evidence.current_tag}-cli`,
      run_url: runId
        ? `https://github.com/${evidence.repo}/actions/runs/${runId}`
        : "",
      attempts: attempts.slice(-3).map((attempt, index) => ({
        attempt: index + 1,
        error_code: String(attempt?.error_code || "RELEASE_NOTES_FAILED"),
        message: sanitizeError(attempt?.message || attempt).slice(0, 600),
        retryable: Boolean(attempt?.retryable),
      })),
      final_error: sanitizeError(finalError).slice(0, 600),
    }),
  });
  if (!response.ok) {
    throw new Error(`failure-report endpoint returned HTTP ${response.status}`);
  }
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : { ok: true };
  } catch {
    return { ok: true };
  }
}

async function reportFailureBestEffort(args) {
  try {
    return await reportFailure(args);
  } catch (error) {
    warn(`Failure notification was not delivered: ${error?.message || error}`);
    return { skipped: true, reason: sanitizeError(error?.message || error) };
  }
}

export async function generateGitHubReleaseNotes({
  repo,
  currentTag,
  targetSha,
  previousTag,
  token = process.env.GITHUB_TOKEN || "",
}) {
  const fallback = (warning = "") => {
    const name = `MemOS CLI ${currentTag}`;
    const body = [
      "## What's Changed",
      ...lines(tryGit(["log", "--format=%s", `${previousTag}..${targetSha}`])).map(
        (subject) => `* ${redact(subject)}`,
      ),
      "",
      `**Full Changelog**: https://github.com/${repo}/compare/${previousTag}...${currentTag}`,
      "",
    ].join("\n");
    assertNoSensitiveContent(name, "local fallback release name");
    assertNoSensitiveContent(body, "local fallback release notes");
    return {
      source: warning ? "local-fallback-after-github-error" : "local-fallback",
      name,
      body,
      warning,
    };
  };
  if (!token) return fallback("GITHUB_TOKEN unavailable; used local preview.");
  try {
    const payload = await fetchJsonWithRetry(
      `https://api.github.com/repos/${repo}/releases/generate-notes`,
      {
        method: "POST",
        headers: {
          accept: "application/vnd.github+json",
          authorization: `Bearer ${token}`,
          "content-type": "application/json",
          "x-github-api-version": "2022-11-28",
        },
        body: JSON.stringify({
          tag_name: currentTag,
          target_commitish: targetSha,
          previous_tag_name: previousTag,
        }),
      },
      { label: "GitHub generated release notes" },
    );
    if (!String(payload.body || "").trim()) {
      fail("GitHub generated release notes response was empty.");
    }
    const name = String(payload.name || `MemOS CLI ${currentTag}`);
    const body = String(payload.body);
    assertNoSensitiveContent(name, "GitHub generated release name");
    assertNoSensitiveContent(body, "GitHub generated release notes");
    return {
      source: "github-generate-notes-api",
      name,
      body,
      warning: "",
    };
  } catch (error) {
    if (String(process.env.ALLOW_OFFLINE_DOCS_PREVIEW || "") !== "true") {
      throw error;
    }
    return fallback(sanitizeError(error?.message || error));
  }
}

export function reviewedReleaseNotesAtRef({ targetSha, currentTag }) {
  const path = `.github/release-notes/${currentTag}.md`;
  const body = tryGit(["show", `${targetSha}:${path}`]);
  if (!body) return null;
  if (body.length < 40) {
    fail(`${path} is too short to be a useful reviewed Release note.`);
  }
  if (body.length > 50000) {
    fail(`${path} exceeds the 50,000 character Release note limit.`);
  }
  if (!/^##\s+\S+/m.test(body)) {
    fail(`${path} must contain at least one level-two Markdown heading.`);
  }
  if (/\b(?:TODO|TBD|PLACEHOLDER)\b/i.test(body)) {
    fail(`${path} still contains TODO/TBD/PLACEHOLDER text.`);
  }
  assertNoSensitiveContent(body, path);
  return { path, body: `${body.trim()}\n` };
}

function docAgentReleaseNotesBody(draft) {
  const output = ["## Changelog", ""];
  for (const category of RELEASE_CATEGORIES) {
    const items = draft.release_items.filter(
      (item) => item.category === category,
    );
    if (!items.length) continue;
    output.push(`### ${category}`, "");
    for (const item of items) output.push(`- ${item.text_en}`);
    output.push("");
  }
  return draft.release_items.length ? output.join("\n").trim() : "";
}

export function composePublicReleaseNotes({
  githubNotes,
  draft,
  reviewedNotes = null,
}) {
  const generatedBody = String(githubNotes?.body || "").trim();
  if (!generatedBody) fail("GitHub What's Changed notes are empty.");
  const docAgentBody = docAgentReleaseNotesBody(draft);
  let source;
  let primaryBody;
  let reviewedPath = "";
  if (reviewedNotes) {
    source = "reviewed-file-plus-github-whats-changed";
    primaryBody = reviewedNotes.body.trim();
    reviewedPath = reviewedNotes.path;
  } else if (docAgentBody) {
    source = "validated-doc-agent-plus-github-whats-changed";
    primaryBody = docAgentBody;
  } else {
    source = "github-whats-changed-after-doc-agent-skip";
    primaryBody = "";
  }
  const body = [primaryBody, generatedBody].filter(Boolean).join("\n\n---\n\n");
  assertNoSensitiveContent(body, "composed public Release notes");
  return {
    source,
    name: String(githubNotes?.name || "MemOS CLI Release"),
    body: `${body.trim()}\n`,
    warning: String(githubNotes?.warning || ""),
    reviewed_path: reviewedPath,
    components: [
      reviewedNotes ? "reviewed_release_notes_file" : "",
      !reviewedNotes && docAgentBody ? "validated_doc_agent_draft" : "",
      "github_whats_changed",
    ].filter(Boolean),
  };
}

export function normalizeDraft(raw) {
  return {
    ok: raw?.ok !== false,
    needs_review: Boolean(raw?.needs_review),
    confidence: String(raw?.confidence || ""),
    warnings: Array.isArray(raw?.warnings)
      ? raw.warnings.map((item) => sanitizeError(item))
      : [],
    candidate_selection: raw?.candidate_selection || {},
    release_items: (Array.isArray(raw?.release_items)
      ? raw.release_items
      : Array.isArray(raw?.items)
        ? raw.items
        : []
    ).map((item) => ({
      category: String(item?.category || "").trim(),
      text_cn: String(item?.text_cn || "").trim(),
      text_en: String(item?.text_en || "").trim(),
      source_refs: Array.isArray(item?.source_refs)
        ? [...new Set(item.source_refs.map((ref) => String(ref).trim()).filter(Boolean))]
        : [],
    })),
  };
}

export function injectDraftFault(
  draft,
  evidence,
  faultCase,
  { validationRound = 1 } = {},
) {
  const value = String(faultCase || "none").trim() || "none";
  if (value === "none" || validationRound !== 1) return draft;
  const injected = {
    ...draft,
    release_items: draft.release_items.map((item) => ({
      ...item,
      source_refs: [...item.source_refs],
    })),
  };
  const first = injected.release_items[0];
  if (!first) return injected;
  if (value === "mixed_language") {
    first.text_en = "修复了 CLI authentication issue。";
  } else if (value === "missing_source_refs") {
    first.source_refs = [];
  } else if (value === "invalid_source_ref") {
    first.source_refs = ["deadbee"];
  } else if (value === "missing_important_commit") {
    const accepted = (evidence.required_source_refs || []).flatMap(
      (required) => required.accepted_refs || [],
    );
    for (const item of injected.release_items) {
      item.source_refs = item.source_refs.filter(
        (ref) =>
          !accepted.some((acceptedRef) =>
            sourceRefMatches(ref, acceptedRef),
          ),
      );
    }
  } else if (value === "thirteen_items") {
    injected.release_items = Array.from(
      { length: MAX_RELEASE_ITEMS + 1 },
      (_, index) => ({
        ...first,
        text_cn: `${first.text_cn}（故障注入 ${index + 1}）`,
        text_en: `${first.text_en} (fault injection ${index + 1})`,
        source_refs: [...first.source_refs],
      }),
    );
  } else if (value === "too_long") {
    first.text_cn = `**CLI 故障注入**：${"用于验证官网更新日志长度保护。".repeat(20)}`;
    first.text_en = `**CLI fault injection**: ${"This text verifies the website changelog length guard. ".repeat(10)}`;
  }
  return injected;
}

function duplicateKey(item) {
  return [item.category, item.text_cn, item.text_en]
    .map((value) =>
      value
        .toLowerCase()
        .replace(/^\*\*[^*]+\*\*\s*[:：]\s*/, "")
        .replace(/[#`*_()[\]{}:：,，。.;；!！?\s-]+/g, " ")
        .trim(),
    )
    .join("|");
}

function looksLikeRawCommit(text) {
  return /\b(feat|fix|perf|refactor|chore|docs|test|ci|build)(\([^)]+\))?!?:\s+/i.test(
    String(text || ""),
  );
}

function stripBoldPrefix(text) {
  return String(text || "")
    .trim()
    .replace(/^\*\*[^*]+\*\*\s*[:：]\s*/, "")
    .trim();
}

function isGenericChineseDocsText(text) {
  const body = stripBoldPrefix(text).replace(/\s+/g, "");
  if (
    /(便于|降低|减少|避免|确保|支持|适配|稳定|同步|处理|接入|配置|提示|定位)/.test(
      body,
    )
  ) {
    return false;
  }
  return /^(新增了|修复了|优化了|增加了|更新了).{1,40}(功能|问题|性能|能力|体验)[。.]?$/.test(
    body,
  );
}

function isGenericEnglishDocsText(text) {
  const body = stripBoldPrefix(text)
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
  if (/\b(to|so|because|when|during|for|with|without)\b/.test(body)) {
    return false;
  }
  return /^(added|fixed|improved|updated|enhanced)\b.{1,60}\b(feature|functionality|issue|bug|problem|performance|capability|experience)\.?$/.test(
    body,
  );
}

function sourceRefMatches(left, right) {
  const a = String(left || "").trim();
  const b = String(right || "").trim();
  if (!a || !b) return false;
  if (a === b) return true;
  if (/^[0-9a-f]{7,40}$/i.test(a) && /^[0-9a-f]{7,40}$/i.test(b)) {
    return a.toLowerCase().startsWith(b.toLowerCase()) ||
      b.toLowerCase().startsWith(a.toLowerCase());
  }
  return false;
}

export function validateDraft(draft, evidence) {
  const issues = [];
  const validRefs = new Set(
    evidence.commits.flatMap((commit) => commit.source_refs || []),
  );
  const userFacingRefs = (evidence.required_source_refs || []).flatMap(
    (required) => required.accepted_refs || [],
  );
  for (const pull of evidence.pull_requests || []) validRefs.add(`#${pull.number}`);
  if (!draft.ok) issues.push({ kind: "draft_not_ok" });
  if (draft.needs_review) issues.push({ kind: "needs_review" });
  if (
    evidence.has_user_facing_product_changes &&
    draft.release_items.length === 0
  ) {
    issues.push({ kind: "empty_release_items" });
  }
  if (
    !evidence.has_user_facing_product_changes &&
    draft.release_items.length > 0
  ) {
    issues.push({ kind: "unexpected_release_items_without_user_changes" });
  }
  if (draft.release_items.length > MAX_RELEASE_ITEMS) {
    issues.push({
      kind: "too_many_release_items",
      actual: draft.release_items.length,
      maximum: MAX_RELEASE_ITEMS,
    });
  }
  const seen = new Map();
  for (const [index, item] of draft.release_items.entries()) {
    const key = duplicateKey(item);
    if (seen.has(key)) {
      issues.push({
        kind: "duplicate_release_item",
        index,
        duplicate_of: seen.get(key),
      });
    } else {
      seen.set(key, index);
    }
    if (!RELEASE_CATEGORIES.includes(item.category)) {
      issues.push({ kind: "invalid_category", index, value: item.category });
    }
    if (!item.text_cn || !CJK_RE.test(item.text_cn)) {
      issues.push({ kind: "invalid_text_cn", index });
    }
    if (!item.text_en || CJK_RE.test(item.text_en)) {
      issues.push({ kind: "invalid_text_en", index });
    }
    if (item.text_cn.length > MAX_TEXT_CN_CHARS) {
      issues.push({ kind: "text_cn_too_long", index });
    }
    if (item.text_en.length > MAX_TEXT_EN_CHARS) {
      issues.push({ kind: "text_en_too_long", index });
    }
    if (looksLikeRawCommit(item.text_cn) || looksLikeRawCommit(item.text_en)) {
      issues.push({ kind: "raw_commit_subject", index });
    }
    if (isGenericChineseDocsText(item.text_cn)) {
      issues.push({ kind: "generic_text_cn", index });
    }
    if (isGenericEnglishDocsText(item.text_en)) {
      issues.push({ kind: "generic_text_en", index });
    }
    if (
      redact(item.text_cn) !== item.text_cn ||
      redact(item.text_en) !== item.text_en ||
      /https?:\/\//i.test(item.text_cn) ||
      /https?:\/\//i.test(item.text_en)
    ) {
      issues.push({ kind: "sensitive_content", index });
    }
    if (!item.source_refs.length) {
      issues.push({ kind: "missing_source_refs", index });
    }
    for (const ref of item.source_refs) {
      if (
        hasSensitiveContent(ref) ||
        /https?:\/\//i.test(String(ref || ""))
      ) {
        issues.push({ kind: "sensitive_source_ref", index });
      }
      if (![...validRefs].some((validRef) => sourceRefMatches(ref, validRef))) {
        issues.push({ kind: "invalid_source_ref", index, ref });
      }
    }
    if (
      evidence.has_user_facing_product_changes &&
      item.source_refs.length > 0 &&
      !item.source_refs.some((ref) =>
        userFacingRefs.some((userFacingRef) =>
          sourceRefMatches(ref, userFacingRef),
        ),
      )
    ) {
      issues.push({
        kind: "non_user_facing_source_refs",
        index,
        source_refs: item.source_refs,
      });
    }
  }
  const covered = draft.release_items.flatMap((item) => item.source_refs);
  const missing = (evidence.required_source_refs || [])
    .filter(
      (required) =>
        !required.accepted_refs.some((acceptedRef) =>
          covered.some((coveredRef) =>
            sourceRefMatches(coveredRef, acceptedRef),
          ),
        ),
    )
    .map((required) => required.short_sha);
  for (const ref of missing) {
    issues.push({ kind: "missing_required_ref", ref });
  }
  return {
    ok: issues.length === 0,
    needs_review: issues.length > 0,
    issue_count: issues.length,
    issues,
    coverage: {
      required_count: evidence.required_source_refs.length,
      covered_required_count:
        evidence.required_source_refs.length - missing.length,
      missing_required_count: missing.length,
      missing_required_refs: missing,
    },
  };
}

function offlineDraft(evidence) {
  const items = evidence.important_commits.slice(0, MAX_RELEASE_ITEMS).map((commit) => ({
    category: /^feat/i.test(commit.subject)
      ? "Added"
      : /^fix|^revert/i.test(commit.subject)
        ? "Fixed"
        : "Improved",
    text_cn: `**CLI 变更 ${commit.short_sha}**：根据该提交证据生成的离线测试预览。`,
    text_en: `**CLI change ${commit.short_sha}**: Offline test preview derived from this commit evidence.`,
    source_refs: [commit.short_sha],
  }));
  return {
    ok: true,
    needs_review: false,
    confidence: "test-only",
    warnings: ["offline test fallback; production requires Doc Agent secrets"],
    candidate_selection: {
      requested_candidate_count: Number(
        evidence.release_note_quality_request?.candidate_count || 1,
      ),
      received_candidate_count: Number(
        evidence.release_note_quality_request?.candidate_count || 1,
      ),
      selected_candidate: 1,
      policy: "offline test fallback",
    },
    release_items: items,
  };
}

function candidateScore(validation, draft) {
  return [
    validation.ok ? 1 : 0,
    validation.coverage.covered_required_count,
    -validation.coverage.missing_required_count,
    -validation.issue_count,
    -Math.abs(Math.min(draft.release_items.length, 10) - 6),
  ];
}

function compareScores(left, right) {
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const difference = Number(left[index] || 0) - Number(right[index] || 0);
    if (difference !== 0) return difference;
  }
  return 0;
}

async function requestOneDraft({
  url,
  token,
  evidence,
  candidateIndex,
  candidateCount,
  validationRound,
  repairContext,
  history,
}) {
  return fetchJsonWithRetry(
    url,
    {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        ...evidence,
        candidate_selection_context: {
          candidate_index: candidateIndex,
          candidate_count: candidateCount,
          selection_policy:
            "Generate an independent candidate; the workflow selects by deterministic evidence and readability checks.",
        },
        workflow_retry_context: {
          attempt: validationRound,
          previous_errors: history,
        },
        repair_context: repairContext,
      }),
    },
    { label: `Doc Agent CLI changelog candidate ${candidateIndex}` },
  );
}

export async function requestDocAgentDraft(evidence) {
  if (!evidence.has_user_facing_product_changes) {
    const draft = normalizeDraft({
      ok: true,
      needs_review: false,
      confidence: "high",
      warnings: [evidence.skip_reason],
      release_items: [],
    });
    return {
      ...draft,
      validation_report: validateDraft(draft, evidence),
      validation_attempt_count: 1,
      repair_attempt_count: 0,
    };
  }
  const url = String(
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL || "",
  ).trim();
  const token = String(
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN || "",
  ).trim();
  if ((!url || !token) && process.env.ALLOW_OFFLINE_DOCS_PREVIEW === "true") {
    const draft = normalizeDraft(offlineDraft(evidence));
    return {
      ...draft,
      validation_report: validateDraft(draft, evidence),
      validation_attempt_count: 1,
      repair_attempt_count: 0,
    };
  }
  if (!url) fail("DOC_AGENT_RELEASE_NOTES_DRAFT_URL secret is required.");
  if (!token) fail("DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN secret is required.");

  const candidateCount = Number(
    evidence.release_note_quality_request?.candidate_count || 3,
  );
  const faultCase = String(
    process.env.RELEASE_FAULT_CASE || "none",
  ).trim() || "none";
  const candidates = [];
  const requestErrors = [];
  for (let candidateIndex = 1; candidateIndex <= candidateCount; candidateIndex += 1) {
    try {
      const payload = await requestOneDraft({
        url,
        token,
        evidence,
        candidateIndex,
        candidateCount,
        validationRound: 1,
        repairContext: null,
        history: [],
      });
      const draft = injectDraftFault(
        normalizeDraft(payload),
        evidence,
        faultCase,
        { validationRound: 1 },
      );
      const validation = validateDraft(draft, evidence);
      candidates.push({
        candidate_index: candidateIndex,
        draft,
        validation,
        score: candidateScore(validation, draft),
      });
    } catch (error) {
      requestErrors.push({
        candidate_index: candidateIndex,
        error: sanitizeError(error?.message || error),
        attempts: Array.isArray(error?.attempts) ? error.attempts : [],
      });
    }
  }
  if (!candidates.length) {
    const exhaustedAttempts = requestErrors.flatMap(
      (item) => item.attempts || [],
    );
    await reportFailureBestEffort({
      evidence,
      attempts: exhaustedAttempts,
      finalError: requestErrors.at(-1)?.error || "no candidate returned",
      phase: "release-notes-candidates",
    });
    fail(
      `Doc Agent returned no candidate after ${candidateCount} independent requests: ${JSON.stringify(requestErrors)}`,
    );
  }
  candidates.sort((left, right) => compareScores(right.score, left.score));
  let selected = candidates[0];
  const selection = {
    requested_candidate_count: candidateCount,
    received_candidate_count: candidates.length,
    selected_candidate: selected.candidate_index,
    policy:
      "best evidence-backed candidate by deterministic coverage, validation, and readability score",
    candidates: candidates.map((candidate) => ({
      candidate_index: candidate.candidate_index,
      ok: candidate.validation.ok,
      score: candidate.score,
      issue_count: candidate.validation.issue_count,
      coverage: candidate.validation.coverage,
    })),
    request_errors: requestErrors,
  };
  if (candidates.length !== candidateCount) {
    const exhaustedAttempts = requestErrors.flatMap(
      (item) => item.attempts || [],
    );
    await reportFailureBestEffort({
      evidence,
      attempts: exhaustedAttempts,
      finalError: `received ${candidates.length}/${candidateCount} candidates`,
      phase: "release-notes-candidates",
    });
    fail(
      `Doc Agent returned only ${candidates.length}/${candidateCount} candidates; refusing to reduce quality silently.`,
    );
  }
  if (selected.validation.ok) {
    return {
      ...selected.draft,
      candidate_selection: selection,
      validation_report: selected.validation,
      validation_attempt_count: 1,
      repair_attempt_count: 0,
    };
  }
  const validationFailures = [];

  const history = [
    {
      validation_round: 1,
      selected_candidate: selected.candidate_index,
      validation: selected.validation,
    },
  ];
  let repairContext = {
    validation_report: selected.validation,
    previous_release_items: selected.draft.release_items,
    instructions: [
      "Repair only the reported validation issues.",
      "Use only facts present in the evidence.",
      "Return concise Added, Improved, or Fixed release_items.",
      "Each item must contain text_cn, text_en, and valid source_refs.",
      "Merge duplicate topics while preserving all source_refs.",
      "Do not expose internal infrastructure or copy raw commit subjects.",
    ],
  };
  for (let repairAttempt = 1; repairAttempt <= MAX_DRAFT_ATTEMPTS; repairAttempt += 1) {
    let payload;
    try {
      payload = await requestOneDraft({
        url,
        token,
        evidence,
        candidateIndex: selected.candidate_index,
        candidateCount,
        validationRound: repairAttempt + 1,
        repairContext,
        history,
      });
    } catch (error) {
      await reportFailureBestEffort({
        evidence,
        attempts: Array.isArray(error?.attempts) ? error.attempts : [],
        finalError: error?.message || error,
        phase: "release-notes-repair-request",
      });
      throw error;
    }
    const draft = injectDraftFault(
      normalizeDraft(payload),
      evidence,
      faultCase,
      { validationRound: repairAttempt + 1 },
    );
    const validation = validateDraft(draft, evidence);
    if (!validation.ok) {
      validationFailures.push({
        error_code: "RELEASE_NOTES_VALIDATION",
        message: JSON.stringify({
          repair_attempt: repairAttempt,
          issues: validation.issues,
        }),
        retryable: false,
      });
    }
    history.push({
      validation_round: repairAttempt + 1,
      selected_candidate: selected.candidate_index,
      validation,
    });
    if (validation.ok) {
      return {
        ...draft,
        candidate_selection: selection,
        validation_report: validation,
        validation_attempt_count: repairAttempt + 1,
        repair_attempt_count: repairAttempt,
      };
    }
    repairContext = {
      validation_report: validation,
      previous_release_items: draft.release_items,
      instructions: repairContext.instructions,
    };
  }
  await reportFailureBestEffort({
    evidence,
    attempts: validationFailures,
    finalError: JSON.stringify(
      history.at(-1)?.validation?.issues || [],
    ),
    phase: "release-notes-validation",
  });
  fail(
    `Doc Agent selected draft failed ${MAX_DRAFT_ATTEMPTS} repair attempts: ${JSON.stringify(
      history.at(-1)?.validation?.issues || [],
    )}`,
  );
}

export function buildDocsPreview(draft, evidence) {
  const side = (language) => {
    const categories = {};
    for (const releaseCategory of RELEASE_CATEGORIES) {
      const changedInfo = draft.release_items
        .filter((item) => item.category === releaseCategory)
        .map((item) => (language === "zh" ? item.text_cn : item.text_en));
      if (changedInfo.length) {
        categories[DOCS_CATEGORIES[releaseCategory]] = [
          {
            type: PRODUCT_TITLE[language],
            changedInfo,
          },
        ];
      }
    }
    return {
      name: evidence.current_tag,
      source: {
        repo: evidence.repo,
        tag: evidence.current_tag,
        previous_tag: evidence.previous_tag,
        release_url: `https://github.com/${evidence.repo}/releases/tag/${evidence.current_tag}`,
        evidence_scope: "whole_repository",
      },
      products: { plugin: categories },
    };
  };
  return {
    source_id: PRODUCT_ID,
    source_repo: evidence.repo,
    previous_tag: evidence.previous_tag,
    current_tag: evidence.current_tag,
    evidence_scope: "whole_repository",
    product_paths: ["**"],
    release_items: draft.release_items,
    docs_action: draft.release_items.length
      ? "preview_plugin_tab_entry"
      : "skip_plugin_tab_entry",
    would_create_docs_pr: false,
    files: [
      "content/cn/plugin-changelog.yml",
      "content/en/plugin-changelog.yml",
    ],
    cn: side("zh"),
    en: side("en"),
  };
}

export function docsPreviewMarkdown(preview, draft, evidence) {
  const output = [
    `# MemOS CLI-${evidence.current_tag}`,
    "",
    `- source: ${evidence.previous_tag}...${evidence.current_tag}`,
    "- evidence_scope: whole_repository",
    "- product_paths: **",
    `- docs_action: ${preview.docs_action}`,
    "- would_create_docs_pr: false",
    "",
  ];
  for (const category of RELEASE_CATEGORIES) {
    const items = draft.release_items.filter(
      (item) => item.category === category,
    );
    if (!items.length) continue;
    output.push(`## ${category}`, "");
    for (const item of items) {
      output.push(`- CN: ${item.text_cn}`);
      output.push(`- EN: ${item.text_en}`);
      output.push(`- refs: ${item.source_refs.join(", ")}`, "");
    }
  }
  if (!draft.release_items.length) {
    output.push(`No Plugin tab entry: ${evidence.skip_reason}`, "");
  }
  return output.join("\n");
}

function setOutput(name, value) {
  const outputFile = process.env.GITHUB_OUTPUT;
  if (outputFile) appendFileSync(outputFile, `${name}=${value}\n`, "utf8");
}

function writeJson(path, value) {
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function releaseContract(repo) {
  return {
    source_id: PRODUCT_ID,
    source_repo: repo,
    release_trigger: "release.published",
    required_webhook_event: "release",
    draft_release_trigger:
      "official main push after an internal or fork PR merge with an all-three-file SemVer increase, or manual workflow_dispatch",
    public_release_body:
      "optional_reviewed_file_or_validated_doc_agent_draft_plus_github_whats_changed",
    reviewed_release_notes_path: ".github/release-notes/v<version>.md",
    reviewed_release_notes_optional: true,
    docs_evidence: "whole_tag_range",
    evidence_scope: "whole_repository",
    product_paths: ["**"],
    docs_files: [
      "content/cn/plugin-changelog.yml",
      "content/en/plugin-changelog.yml",
    ],
    live_release_policy: {
      default_entry:
        "automatic official main push with an all-three-file SemVer increase",
      manual_target_ref: "main",
      trusted_main_push_target: "after commit from the official main push",
      manual_exact_confirmation: "PUBLISH v<version>",
      automatic_merge_confirmation:
        "trusted official main push plus a validated three-file SemVer increase",
      creates_draft_release: true,
      manual_publish_required: true,
      direct_publish_allowed: false,
    },
    dry_run_side_effects: {
      creates_tag: false,
      creates_github_release: false,
      creates_docs_pr: false,
      deploys_pre: false,
      deploys_gray: false,
      deploys_production: false,
    },
  };
}

function inspectionReadme({
  state,
  evidence,
  draft,
  preview,
  releaseNotes,
}) {
  const coverage = draft.validation_report?.coverage || {};
  const selection = draft.candidate_selection || {};
  return [
    "# MemOS CLI release inspection",
    "",
    "## Decision",
    "",
    `- inspection_kind: ${state.inspectionKind}`,
    `- release_source_mode: ${state.releaseSourceMode}`,
    `- quality_ok: ${Boolean(draft.validation_report?.ok)}`,
    "- publish_blocked: false",
    `- docs_action: ${preview.docs_action}`,
    `- has_user_facing_product_changes: ${Boolean(
      evidence.has_user_facing_product_changes,
    )}`,
    "",
    "## Release boundary",
    "",
    `- previous_tag: ${evidence.previous_tag}`,
    `- current_tag: ${evidence.current_tag}`,
    `- target_ref_input: ${state.targetRefInput}`,
    `- target_ref_resolved: ${state.targetRefResolved}`,
    `- target_sha: ${state.targetSha}`,
    `- existing_tag_status: ${state.existingTagStatus}`,
    `- existing_tag_sha: ${state.existingTagSha || "<absent>"}`,
    "- source_id: memos-cloud-cli",
    "- evidence_scope: whole_repository",
    "- product_paths: **",
    "",
    "## Quality result",
    "",
    `- requested_candidate_count: ${
      selection.requested_candidate_count || 0
    }`,
    `- received_candidate_count: ${selection.received_candidate_count || 0}`,
    `- selected_candidate: ${
      selection.selected_candidate ?? selection.selected_index ?? ""
    }`,
    `- coverage_required_count: ${coverage.required_count || 0}`,
    `- coverage_missing_required_count: ${
      coverage.missing_required_count || 0
    }`,
    `- repair_attempt_count: ${draft.repair_attempt_count || 0}`,
    `- release_notes_source: ${releaseNotes.source}`,
    `- reviewed_release_notes_path: ${
      releaseNotes.reviewed_path || "<not provided; Doc Agent generated the summary>"
    }`,
    "",
    "## Review files",
    "",
    "- `github-release-notes.md` / `release-notes.md`: public GitHub Release body preview.",
    "- `release-notes-source.json`: public body provenance, components, target commit, and version range.",
    "- `evidence.json`: redacted whole-repository tag-range evidence.",
    "- `release-notes-draft.json`: accepted bilingual items and internal source refs.",
    "- `docs-preview.md` / `docs-preview.json`: Plugin tab preview.",
    "- `quality-report.json`: deterministic validation, coverage, candidates, and repair history.",
    "- `release-contract.json`: trigger, target files, Draft-first policy, and side-effect contract.",
    "",
    "## Dry-run side effects",
    "",
    "This inspection does not create a tag, GitHub Release, MemOS-Docs PR, or deployment.",
    "",
  ].join("\n");
}

function writeBlockedInspection(root, state, error) {
  const reason = sanitizeError(error?.message || error);
  const repo = state.repo || "MemTensor/MemOS-Cloud-CLI";
  const placeholders = [
    [
      "github-release-notes.md",
      `# GitHub Release notes unavailable\n\nPreparation stopped before a valid preview was produced.\n`,
    ],
    [
      "release-notes.md",
      `# GitHub Release notes unavailable\n\nPreparation stopped before a valid preview was produced.\n`,
    ],
    [
      "docs-preview.md",
      `# MemOS CLI changelog preview blocked\n\nThe release quality gate stopped before website copy could be accepted.\n`,
    ],
    [
      "README.md",
      [
        "# MemOS CLI release inspection",
        "",
        "## Decision",
        "",
        `- inspection_kind: ${state.inspectionKind || "release_preview"}`,
        "- quality_ok: false",
        "- publish_blocked: true",
        `- publish_block_reason: ${reason}`,
        `- phase: ${state.phase || "prepare"}`,
        `- existing_tag_status: ${state.existingTagStatus || "unknown"}`,
        `- existing_tag_sha: ${state.existingTagSha || "<unknown>"}`,
        "",
        "No tag, GitHub Release, MemOS-Docs PR, or deployment was created.",
        "",
      ].join("\n"),
    ],
  ];
  for (const [name, contents] of placeholders) {
    const path = join(root, name);
    if (!existsSync(path)) writeFileSync(path, contents, "utf8");
  }
  const evidencePath = join(root, "evidence.json");
  if (!existsSync(evidencePath)) {
    writeJson(evidencePath, {
      product_id: PRODUCT_ID,
      repo,
      previous_tag: state.previousTag || "",
      current_tag: state.currentTag || "",
      target_version: state.currentTag || "",
      git_ref: state.targetSha || "",
      evidence_scope: "whole_repository",
      product_paths: ["**"],
      collection_status: "blocked_before_complete_evidence",
    });
  }
  const previewPath = join(root, "docs-preview.json");
  if (!existsSync(previewPath)) {
    writeJson(previewPath, {
      source_id: PRODUCT_ID,
      source_repo: repo,
      previous_tag: state.previousTag || "",
      current_tag: state.currentTag || "",
      evidence_scope: "whole_repository",
      product_paths: ["**"],
      docs_action: "blocked_by_quality_gate",
      would_create_docs_pr: false,
      files: [
        "content/cn/plugin-changelog.yml",
        "content/en/plugin-changelog.yml",
      ],
    });
  }
  writeJson(join(root, "release-notes-draft.json"), {
    ok: false,
    needs_review: true,
    release_items: [],
    phase: state.phase || "prepare",
    error: reason,
  });
  writeJson(join(root, "release-notes-source.json"), {
    source: "blocked_before_release_notes",
    reviewed_path: "",
    components: [],
    target_sha: state.targetSha || "",
    current_tag: state.currentTag || "",
    previous_tag: state.previousTag || "",
    needs_review: true,
  });
  writeJson(join(root, "quality-report.json"), {
    ok: false,
    needs_review: true,
    publish_blocked: true,
    publish_block_reason: reason,
    source_id: PRODUCT_ID,
    previous_tag: state.previousTag || "",
    current_tag: state.currentTag || "",
    target_sha: state.targetSha || "",
    evidence_scope: "whole_repository",
    product_paths: ["**"],
    inspection_kind: state.inspectionKind || "release_preview",
    release_source_mode: state.releaseSourceMode || "manual_dispatch",
    existing_tag_status: state.existingTagStatus || "unknown",
    existing_tag_sha: state.existingTagSha || "",
    phase: state.phase || "prepare",
    fault_case: state.faultCase || "none",
    error: reason,
  });
  writeJson(join(root, "release-contract.json"), releaseContract(repo));
}

async function main() {
  const outputBase = process.env.RUNNER_TEMP || tmpdir();
  const outputName = process.env.RUNNER_TEMP
    ? "memos-cloud-cli-release-inspection"
    : `memos-cloud-cli-release-inspection-${
        process.env.GITHUB_RUN_ID || randomUUID().slice(0, 8)
      }`;
  const root = join(
    outputBase,
    outputName,
  );
  mkdirSync(root, { recursive: true });
  setOutput("inspection_dir", root);
  const state = {
    repo:
      String(process.env.GITHUB_REPOSITORY || "").trim() ||
      "MemTensor/MemOS-Cloud-CLI",
    phase: "validate-inputs",
    releaseSourceMode: "manual_dispatch",
    inspectionKind:
      String(process.env.RELEASE_CONTRACT_FIXTURE || "").toLowerCase() ===
      "true"
        ? "synthetic_contract_fixture"
        : "release_preview",
  };

  try {
    const version = cleanVersion(process.env.RELEASE_VERSION);
    const currentTag = `v${version}`;
    const targetRef = String(process.env.TARGET_REF || "main").trim() || "main";
    const dryRun = String(process.env.DRY_RUN || "true").toLowerCase();
    const releaseSourceMode = validateReleaseSourceMode(
      process.env.RELEASE_SOURCE_MODE,
    );
    const faultCase = validateFaultCase({
      dryRun,
      faultCase: process.env.RELEASE_FAULT_CASE,
    });
    state.faultCase = faultCase;
    state.currentTag = currentTag;
    state.targetRefInput = targetRef;
    state.releaseSourceMode = releaseSourceMode;
    validatePublishConfirmation({
      dryRun,
      version,
      confirmation: process.env.PUBLISH_CONFIRMATION,
      releaseSourceMode,
    });
    validateDraftFirstRelease({
      dryRun,
      createDraftRelease: process.env.CREATE_DRAFT_RELEASE,
    });
    validateReleaseTarget({ dryRun, targetRef, releaseSourceMode });
    validateDocAgentConfiguration({
      allowOffline:
        String(process.env.ALLOW_OFFLINE_DOCS_PREVIEW || "").toLowerCase() ===
        "true",
    });

    state.phase = "resolve-release-source";
    const target = resolveRef(targetRef);
    state.targetSha = target.sha;
    state.targetRefResolved = target.ref;
    const defaultBranch =
      String(process.env.DEFAULT_BRANCH || "main").trim() || "main";
    const defaultBranchSha = tryGit([
      "rev-parse",
      "--verify",
      `origin/${defaultBranch}^{commit}`,
    ]);
    if (dryRun !== "true" && !defaultBranchSha) {
      fail(`cannot resolve origin/${defaultBranch} for a live release.`);
    }
    const targetIsDefaultBranchAncestor = Boolean(
      defaultBranchSha &&
        gitSucceeds([
          "merge-base",
          "--is-ancestor",
          target.sha,
          defaultBranchSha,
        ]),
    );
    validateLiveReleaseSource({
      dryRun,
      workflowRef: process.env.GITHUB_REF,
      defaultBranch,
      targetSha: target.sha,
      defaultBranchSha,
      targetIsDefaultBranchAncestor,
      releaseSourceMode,
    });
    validateVersionSources(version, versionSources(target.sha));
    const existingCurrentTag = tryGit([
      "rev-parse",
      "--verify",
      `refs/tags/${currentTag}^{commit}`,
    ]);
    state.existingTagSha = existingCurrentTag;
    state.existingTagStatus = existingCurrentTag
      ? existingCurrentTag === target.sha
        ? "matches_target"
        : "conflicts_target"
      : "absent";
    if (existingCurrentTag && existingCurrentTag !== target.sha) {
      fail(
        `${currentTag} already points to ${existingCurrentTag}, expected ${target.sha}`,
      );
    }
    const tags = lines(tryGit(["tag", "--list", "v*"]));
    validateReleaseVersionOrder(version, currentTag, tags);
    const previousTag = findPreviousTag(version, currentTag, tags);
    if (!previousTag) {
      fail(
        `cannot find a previous SemVer tag before ${currentTag}. ` +
          "For the first automated release, create the verified v1.0.6 baseline tag first.",
      );
    }
    state.previousTag = previousTag;

    state.phase = "collect-evidence";
    const evidence = collectCliEvidence({
      previousTag,
      currentTag,
      currentRef: target.sha,
      targetVersion: version,
      repo: state.repo,
    });
    evidence.release_state = {
      existing_tag_status: state.existingTagStatus,
      existing_tag_sha: state.existingTagSha,
      publish_blocked: false,
      publish_block_reason: "",
    };
    evidence.inspection_kind = state.inspectionKind;
    const evidenceFile = join(root, "evidence.json");
    writeJson(evidenceFile, evidence);

    state.phase = "generate-github-whats-changed";
    const githubNotes = await generateGitHubReleaseNotes({
      repo: state.repo,
      currentTag,
      targetSha: target.sha,
      previousTag,
    });

    state.phase = "draft-plugin-changelog";
    const draft = await requestDocAgentDraft(evidence);
    if (!draft.validation_report?.ok) {
      fail("CLI changelog draft did not pass deterministic validation.");
    }
    state.phase = "compose-public-release-notes";
    const reviewedNotes = reviewedReleaseNotesAtRef({
      targetSha: target.sha,
      currentTag,
    });
    const releaseNotes = composePublicReleaseNotes({
      githubNotes,
      draft,
      reviewedNotes,
    });
    const releaseNotesFile = join(root, "github-release-notes.md");
    writeFileSync(releaseNotesFile, releaseNotes.body, "utf8");
    writeFileSync(join(root, "release-notes.md"), releaseNotes.body, "utf8");
    writeJson(join(root, "release-notes-source.json"), {
      source: releaseNotes.source,
      reviewed_path: releaseNotes.reviewed_path,
      components: releaseNotes.components,
      target_sha: target.sha,
      current_tag: currentTag,
      previous_tag: previousTag,
      needs_review: Boolean(draft.needs_review),
    });
    const preview = buildDocsPreview(draft, evidence);

    state.phase = "write-inspection";
    const previewFile = join(root, "docs-preview.json");
    const previewMarkdownFile = join(root, "docs-preview.md");
    const qualityReportFile = join(root, "quality-report.json");
    const contractFile = join(root, "release-contract.json");
    const acceptedDraftFile = join(root, "release-notes-draft.json");
    writeJson(previewFile, preview);
    writeFileSync(
      previewMarkdownFile,
      docsPreviewMarkdown(preview, draft, evidence),
      "utf8",
    );
    writeJson(acceptedDraftFile, {
      ok: draft.validation_report.ok,
      needs_review: draft.needs_review,
      confidence: draft.confidence,
      release_items: draft.release_items,
      candidate_selection: draft.candidate_selection,
      validation_report: draft.validation_report,
      validation_attempt_count: draft.validation_attempt_count,
      repair_attempt_count: draft.repair_attempt_count,
      warnings: draft.warnings,
    });
    writeJson(qualityReportFile, {
      ok: draft.validation_report.ok,
      needs_review: draft.needs_review,
      publish_blocked: false,
      publish_block_reason: "",
      source_id: PRODUCT_ID,
      previous_tag: previousTag,
      current_tag: currentTag,
      target_sha: target.sha,
      evidence_scope: "whole_repository",
      product_paths: ["**"],
      inspection_kind: state.inspectionKind,
      release_source_mode: state.releaseSourceMode,
      existing_tag_status: state.existingTagStatus,
      existing_tag_sha: state.existingTagSha,
      has_product_changes: evidence.has_product_changes,
      has_user_facing_product_changes:
        evidence.has_user_facing_product_changes,
      docs_action: preview.docs_action,
      fault_case: faultCase,
      release_notes_source: releaseNotes.source,
      release_notes_reviewed_path: releaseNotes.reviewed_path,
      release_notes_components: releaseNotes.components,
      validation_attempt_count: draft.validation_attempt_count,
      repair_attempt_count: draft.repair_attempt_count,
      validation: draft.validation_report,
      coverage: draft.validation_report.coverage,
      candidate_selection: draft.candidate_selection,
      methodology: RELEASE_NOTE_METHODS,
      warnings: [...draft.warnings, releaseNotes.warning].filter(Boolean),
    });
    writeJson(contractFile, releaseContract(state.repo));
    writeFileSync(
      join(root, "README.md"),
      inspectionReadme({
        state,
        evidence,
        draft,
        preview,
        releaseNotes,
      }),
      "utf8",
    );

    setOutput("current_tag", currentTag);
    setOutput("previous_tag", previousTag);
    setOutput("target_ref", target.ref);
    setOutput("target_sha", target.sha);
    setOutput("release_notes_file", releaseNotesFile);
    setOutput("release_notes_source", releaseNotes.source);
    setOutput("docs_action", preview.docs_action);
    setOutput("validation_attempt_count", draft.validation_attempt_count);
    setOutput("repair_attempt_count", draft.repair_attempt_count);
    console.log(
      `Prepared ${PRODUCT_ID} ${previousTag}...${currentTag} inspection at ${root}`,
    );
  } catch (error) {
    writeBlockedInspection(root, state, error);
    throw error;
  }
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  main().catch((error) => {
    console.error(`::error::${sanitizeError(error?.message || error)}`);
    process.exitCode = 1;
  });
}
