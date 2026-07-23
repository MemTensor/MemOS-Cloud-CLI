import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  cleanVersion,
  compareSemver,
  ensureSourceHint,
  reportExternalFailureFromEnv,
  requestDraft,
  resolvePreviousRef,
  validateManualNotes,
} from "./draft-cli-release-notes.mjs";

const evidence = { repo: "MemTensor/MemOS-Cloud-CLI", current_tag: "v1.0.6", target_version: "v1.0.6" };
const response = (status, body) => ({ status, ok: status >= 200 && status < 300, async text() { return JSON.stringify(body); } });

test("CLI manual notes remain evidence backed", () => {
  const notes = `## Changelog\n\n### Added\n- command\n\n<!-- doc-agent-release-notes-json\n{"items":[{"text_cn":"新增命令","text_en":"Added command","source_refs":["abc1234"]}],"coverage":{"needs_review":false}}\n-->`;
  assert.equal(validateManualNotes(notes), notes);
  assert.match(ensureSourceHint(notes), /source-id=memos-cloud-cli/);
  assert.equal(cleanVersion("v1.0.6"), "1.0.6");
});

test("CLI SemVer comparison handles prerelease numbers and ignores build metadata", () => {
  assert.equal(compareSemver("1.0.0-beta.10", "1.0.0-beta.9") > 0, true);
  assert.equal(compareSemver("1.0.0-beta.20", "1.0.0-beta.19") > 0, true);
  assert.equal(compareSemver("1.0.0", "1.0.0-beta.99") > 0, true);
  assert.equal(compareSemver("1.0.0-beta.1+build.2", "1.0.0-beta.1+build.1"), 0);
  assert.equal(compareSemver("1.0.0-alpha.1", "1.0.0-alpha.beta") < 0, true);
});

test("CLI previous tag selection uses SemVer precedence for prerelease numbers", () => {
  const directory = mkdtempSync(join(tmpdir(), "cli-semver-tags-"));
  const previousCwd = process.cwd();
  try {
    process.chdir(directory);
    execFileSync("git", ["init"], { stdio: "ignore" });
    execFileSync("git", ["config", "user.name", "test"], { stdio: "ignore" });
    execFileSync("git", ["config", "user.email", "test@example.invalid"], { stdio: "ignore" });
    writeFileSync("package.json", '{"private":true}\n', "utf8");
    execFileSync("git", ["add", "package.json"], { stdio: "ignore" });
    execFileSync("git", ["commit", "-m", "init"], { stdio: "ignore" });
    for (const tag of [
      "v1.0.0-beta.1",
      "v1.0.0-beta.2",
      "v1.0.0-beta.9",
      "v1.0.0-beta.10",
      "v1.0.0-beta.19",
    ]) {
      execFileSync("git", ["tag", tag], { stdio: "ignore" });
    }

    assert.equal(resolvePreviousRef("1.0.0-beta.10", "v1.0.0-beta.10"), "v1.0.0-beta.9");
    assert.equal(resolvePreviousRef("1.0.0-beta.20", "v1.0.0-beta.20"), "v1.0.0-beta.19");
  } finally {
    process.chdir(previousCwd);
    rmSync(directory, { recursive: true, force: true });
  }
});

test("CLI external retries are reported after the third attempt", async () => {
  const directory = mkdtempSync(join(tmpdir(), "cli-release-failure-"));
  const previous = { ...process.env };
  try {
    for (const attempt of [1, 2, 3]) writeFileSync(join(directory, `${attempt}.log`), `npm failure ${attempt}`);
    Object.assign(process.env, {
      RELEASE_FAILURE_PHASE: "npm-publish",
      RELEASE_FAILURE_ATTEMPT_DIR: directory,
      RELEASE_VERSION: "1.0.6",
      RELEASE_TAG: "v1.0.6",
      DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN: "test-token",
      DOC_AGENT_RELEASE_FAILURE_URL: "https://example.invalid/internal/release-workflow/failure",
    });
    let report;
    await reportExternalFailureFromEnv({
      fetchImpl: async (_url, options) => { report = JSON.parse(options.body); return response(200, { ok: true }); },
    });
    assert.equal(report.phase, "npm-publish");
    assert.equal(report.attempts.length, 3);
  } finally {
    process.env = previous;
    rmSync(directory, { recursive: true, force: true });
  }
});

test("CLI retries transient draft failures and reports the third", async () => {
  const previous = { ...process.env };
  try {
    Object.assign(process.env, {
      DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN: "test-token",
      DOC_AGENT_RELEASE_NOTES_DRAFT_URL: "https://example.invalid/internal/release-notes/draft",
      DOC_AGENT_RELEASE_FAILURE_URL: "https://example.invalid/internal/release-workflow/failure",
    });
    const calls = [];
    const fetchImpl = async (url, options) => {
      calls.push({ url, body: JSON.parse(options.body) });
      return url.includes("/failure") ? response(200, { ok: true }) : response(503, { detail: "busy" });
    };
    await assert.rejects(requestDraft(evidence, { fetchImpl, sleep: async () => {} }), /attempt 3/);
    assert.equal(calls.filter((item) => item.url.includes("/failure")).length, 1);
  } finally {
    process.env = previous;
  }
});
