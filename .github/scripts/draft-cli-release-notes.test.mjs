import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  cleanVersion,
  compareSemver,
  docsPreviewFromDraft,
  ensureSourceHint,
  manualDraftFromEvidence,
  postprocessDraftFromEvidence,
  qualityReportFromDraft,
  reportExternalFailureFromEnv,
  requestDraft,
  requestValidatedDraft,
  RELEASE_NOTE_QUALITY_REQUEST,
  resolvePreviousRef,
  validateManualNotes,
} from "./draft-cli-release-notes.mjs";

const evidence = { repo: "MemTensor/MemOS-Cloud-CLI", current_tag: "v1.0.6", target_version: "v1.0.6" };
const cliEvidence = {
  ...evidence,
  release_note_quality_request: RELEASE_NOTE_QUALITY_REQUEST,
  commits: [
    {
      sha: "abc1234abc1234abc1234abc1234abc1234abc1",
      short_sha: "abc1234",
      subject: "feat: add CLI binary installer",
    },
  ],
  pull_requests: [],
};
const response = (status, body) => ({ status, ok: status >= 200 && status < 300, async text() { return JSON.stringify(body); } });

test("CLI manual notes remain evidence backed", () => {
  const notes = `## Changelog\n\n### Added\n- command\n\n<!-- doc-agent-release-notes-json\n{"items":[{"category":"Added","text_cn":"新增命令","text_en":"Added command","source_refs":["abc1234"]}],"coverage":{"needs_review":false}}\n-->`;
  assert.equal(validateManualNotes(notes), notes);
  assert.match(ensureSourceHint(notes), /source-id=memos-cloud-cli/);
  assert.equal(cleanVersion("v1.0.6"), "1.0.6");
});

test("CLI manual notes cannot bypass language or source-ref validation", () => {
  const mixedLanguageNotes = `## Changelog\n\n### Added\n- command\n\n<!-- doc-agent-release-notes-json\n{"items":[{"category":"Added","text_cn":"新增命令","text_en":"Added 命令","source_refs":["abc1234"]}],"coverage":{"needs_review":false}}\n-->`;
  assert.throws(() => validateManualNotes(mixedLanguageNotes), /Chinese text in text_cn and English text in text_en/);

  const invalidRefNotes = `## Changelog\n\n### Added\n- command\n\n<!-- doc-agent-release-notes-json\n{"items":[{"category":"Added","text_cn":"新增命令","text_en":"Added command","source_refs":["not a ref"]}],"coverage":{"needs_review":false}}\n-->`;
  assert.throws(() => validateManualNotes(invalidRefNotes), /invalid categories, text, or source_refs/);
});

test("CLI manual notes cannot bypass docs readability validation", () => {
  const longNotes = `## Changelog\n\n### Improved\n- command\n\n<!-- doc-agent-release-notes-json\n{"items":[{"category":"Improved","text_cn":"**CLI 安装器优化**：${"用于发布说明质量验证的重复中文描述。".repeat(12)}","text_en":"**CLI installer improvements**: ${"This repeated English detail is intentionally too verbose for a changelog bullet. ".repeat(6)}","source_refs":["abc1234"]}],"coverage":{"needs_review":false}}\n-->`;
  assert.throws(() => validateManualNotes(longNotes), /concise enough/);
});

test("CLI manual notes are reconciled against real git evidence", () => {
  const validNotes = `## Changelog\n\n### Added\n- command\n\n<!-- doc-agent-release-notes-json\n{"items":[{"category":"Added","text_cn":"新增命令","text_en":"Added command","source_refs":["abc1234"]}],"coverage":{"needs_review":false}}\n-->`;
  const validDraft = manualDraftFromEvidence(cliEvidence, validNotes);
  assert.equal(validDraft.ok, true);
  assert.equal(validDraft.coverage.missing_required_count, 0);
  assert.equal(validDraft.coverage.invalid_source_refs.length, 0);
  assert.equal(validDraft.validation_attempt_count, 1);
  assert.equal(validDraft.repair_attempt_count, 0);

  const inventedRefNotes = validNotes.replaceAll("abc1234", "deadbee");
  const invalidDraft = manualDraftFromEvidence(cliEvidence, inventedRefNotes);
  assert.equal(invalidDraft.ok, false);
  assert.deepEqual(invalidDraft.coverage.invalid_source_refs, ["deadbee"]);
  assert.equal(invalidDraft.coverage.missing_required_count, 1);
});

test("CLI quality report is compact, inspectable, and fail-closed", () => {
  const draft = manualDraftFromEvidence(
    cliEvidence,
    `## Changelog\n\n### Added\n- command\n\n<!-- doc-agent-release-notes-json\n{"items":[{"category":"Added","text_cn":"新增命令","text_en":"Added command","source_refs":["abc1234"]}],"coverage":{"needs_review":false}}\n-->`,
  );
  const report = qualityReportFromDraft(draft, {
    targetVersion: "1.0.7",
    previousRef: "v1.0.6",
    currentTag: "v1.0.7",
    currentRef: "abc1234",
    draftUsed: false,
  });
  assert.equal(report.schema, "memos.plugin.release_notes.quality_report.v1");
  assert.equal(report.ok, true);
  assert.equal(report.needs_review, false);
  assert.equal(report.item_count, 1);
  assert.equal(report.missing_required_count, 0);
  assert.equal(report.limits.max_items, 12);
  assert.equal(report.limits.max_repair_attempts, 3);
  assert.equal(report.draft_used, false);
});

test("CLI requests multi-candidate release-note quality from the draft service", () => {
  assert.equal(RELEASE_NOTE_QUALITY_REQUEST.candidate_count, 3);
  assert.match(RELEASE_NOTE_QUALITY_REQUEST.selection_policy.join("\n"), /source_ref validity/);
  assert.equal(RELEASE_NOTE_QUALITY_REQUEST.repair_policy.max_repair_attempts, 3);
});

test("CLI postprocess rejects mixed-language output and missing important refs", () => {
  const draft = postprocessDraftFromEvidence(cliEvidence, {
    ok: true,
    needs_review: false,
    coverage: { needs_review: false },
    release_items: [
      {
        category: "Added",
        text_cn: "新增 CLI 安装器",
        text_en: "Added CLI 安装器",
        source_refs: ["deadbee"],
      },
    ],
  });
  assert.equal(draft.ok, false);
  assert.equal(draft.needs_review, true);
  assert.deepEqual(draft.coverage.invalid_source_refs, ["deadbee"]);
  assert.equal(draft.coverage.missing_required_count, 1);
  assert.equal(draft.language_issues.length, 1);
});

test("CLI postprocess rejects docs output that is too fragmented", () => {
  const noisyItems = Array.from({ length: 13 }, (_item, index) => ({
    category: "Improved",
    text_cn: `**CLI 优化 ${index + 1}**：优化发布说明展示效果。`,
    text_en: `**CLI improvement ${index + 1}**: Refined release-note presentation.`,
    source_refs: ["abc1234"],
  }));
  const draft = postprocessDraftFromEvidence(cliEvidence, {
    ok: true,
    needs_review: false,
    coverage: { needs_review: false },
    release_items: noisyItems,
  });

  assert.equal(draft.ok, false);
  assert.equal(draft.needs_review, true);
  assert.ok(draft.readability_issues.some((issue) => issue.field === "release_items"));
  assert.ok(draft.validation_report.issues.some((issue) => issue.field === "release_items"));
});

test("CLI postprocess rejects docs bullets that are too long", () => {
  const draft = postprocessDraftFromEvidence(cliEvidence, {
    ok: true,
    needs_review: false,
    coverage: { needs_review: false },
    release_items: [
      {
        category: "Improved",
        text_cn: `**CLI 安装器优化**：${"用于发布说明质量验证的重复中文描述。".repeat(12)}`,
        text_en: `**CLI installer improvements**: ${"This repeated English detail is intentionally too verbose for a changelog bullet. ".repeat(6)}`,
        source_refs: ["abc1234"],
      },
    ],
  });

  assert.equal(draft.ok, false);
  assert.equal(draft.needs_review, true);
  assert.ok(draft.readability_issues.some((issue) => issue.field === "text_cn"));
  assert.ok(draft.readability_issues.some((issue) => issue.field === "text_en"));
  assert.ok(draft.validation_report.issues.some((issue) => issue.field === "text_en"));
});

test("CLI repairs structured needs-review drafts with validation context", async () => {
  const previous = { ...process.env };
  try {
    Object.assign(process.env, {
      DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN: "test-token",
      DOC_AGENT_RELEASE_NOTES_DRAFT_URL: "https://example.invalid/internal/release-notes/draft",
    });
    const calls = [];
    const fetchImpl = async (_url, options) => {
      const body = JSON.parse(options.body);
      calls.push(body);
      if (calls.length === 1) {
        return response(200, {
          ok: false,
          needs_review: true,
          coverage: { needs_review: true },
          release_items: [
            {
              category: "Added",
              text_cn: "新增 CLI 安装器",
              text_en: "Added CLI 安装器",
              source_refs: ["abc1234"],
            },
          ],
        });
      }
      return response(200, {
        ok: true,
        needs_review: false,
        confidence: "high",
        coverage: { needs_review: false },
        release_items: [
          {
            category: "Added",
            text_cn: "新增 CLI 二进制安装器",
            text_en: "Added the CLI binary installer.",
            source_refs: ["abc1234"],
          },
        ],
      });
    };
    const draft = await requestValidatedDraft(cliEvidence, { fetchImpl, sleep: async () => {} });
    assert.equal(draft.ok, true);
    assert.equal(draft.repair_attempt_count, 1);
    assert.equal(calls[0].release_note_quality_request.candidate_count, 3);
    assert.equal(calls[1].release_note_repair_context.validation_report.issue_count, 1);
  } finally {
    process.env = previous;
  }
});

test("CLI docs preview renders plugin changelog entries from validated items", () => {
  const draft = postprocessDraftFromEvidence(cliEvidence, {
    ok: true,
    needs_review: false,
    coverage: { needs_review: false },
    release_items: [
      {
        category: "Added",
        text_cn: "新增 CLI 二进制安装器",
        text_en: "Added the CLI binary installer.",
        source_refs: ["abc1234"],
      },
    ],
  });
  const preview = docsPreviewFromDraft(draft, { targetVersion: "1.0.7", publishedAt: "2026-07-24T02:00:00Z" });
  assert.equal(preview.entries.cn.name, "v1.0.7");
  assert.equal(preview.entries.cn.date, "2026-07-24");
  assert.equal(preview.entries.cn.products.plugin["New Features"][0].type, "MemOS CLI");
  assert.deepEqual(preview.entries.en.products.plugin["New Features"][0].changedInfo, ["Added the CLI binary installer."]);
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

test("CLI exhausted draft failures redact configured URLs and tokens", async () => {
  const previous = { ...process.env };
  try {
    Object.assign(process.env, {
      DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN: "test-token",
      DOC_AGENT_RELEASE_NOTES_DRAFT_URL: "https://example.invalid/internal/release-notes/draft",
      DOC_AGENT_RELEASE_FAILURE_URL: "https://example.invalid/internal/release-workflow/failure",
    });
    const calls = [];
    const fetchImpl = async (url, options) => {
      if (url.includes("/failure")) {
        calls.push({ url, body: JSON.parse(options.body) });
        return response(200, { ok: true });
      }
      throw Object.assign(new Error("connect ECONNREFUSED https://example.invalid/internal/release-notes/draft with Bearer test-token"), {
        retryable: true,
      });
    };
    await assert.rejects(requestDraft(evidence, { fetchImpl, sleep: async () => {} }), /https:\/\/\*\*\*/);
    const report = calls[0].body;
    assert.equal(report.attempts.length, 3);
    assert.doesNotMatch(JSON.stringify(report), /example\.invalid|internal\/release-notes|test-token/);
  } finally {
    process.env = previous;
  }
});
