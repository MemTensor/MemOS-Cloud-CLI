import assert from "node:assert/strict";
import test from "node:test";

import {
  DOC_AGENT_SOURCE_ID,
  docAgentSourceIds,
  inspectReleaseInventory,
} from "./validate-github-release-inventory.mjs";

function release(overrides = {}) {
  return {
    id: 107,
    tag_name: "v1.0.7",
    draft: false,
    prerelease: false,
    target_commitish: "abc123",
    body: `## Changelog\n\n<!-- doc-agent: source-id=${DOC_AGENT_SOURCE_ID} -->`,
    created_at: "2026-07-27T00:00:00Z",
    ...overrides,
  };
}

test("CLI inventory accepts one exact release and source id", () => {
  const report = inspectReleaseInventory({
    pages: [[release()]],
    tag: "v1.0.7",
    expectedDraft: false,
    expectedPrerelease: false,
    expectedTargetCommitish: "abc123",
  });
  assert.equal(report.ok, true);
  assert.deepEqual(docAgentSourceIds(release().body), ["memos-cloud-cli"]);
});

test("CLI inventory fails closed on duplicate releases including drafts", () => {
  const report = inspectReleaseInventory({
    pages: [[release(), release({ id: 108, draft: true })]],
    tag: "v1.0.7",
    expectedDraft: false,
    expectedPrerelease: false,
  });
  assert.equal(report.ok, false);
  assert.equal(report.state, "ambiguous");
  assert.match(report.errors[0], /2 GitHub Releases/);
});

test("CLI inventory verifies target, flags, and source routing", () => {
  const report = inspectReleaseInventory({
    pages: [[release({
      draft: true,
      prerelease: true,
      target_commitish: "wrong",
      body: "<!-- doc-agent: source-id=wrong-source -->",
    })]],
    tag: "v1.0.7",
    expectedDraft: false,
    expectedPrerelease: false,
    expectedTargetCommitish: "abc123",
  });
  assert.equal(report.ok, false);
  assert.equal(report.errors.length, 4);
});

test("CLI inventory can require post-create visibility", () => {
  const report = inspectReleaseInventory({
    pages: [[]],
    tag: "v1.0.7",
    expectedDraft: false,
    expectedPrerelease: false,
    requireExisting: true,
  });
  assert.equal(report.ok, false);
  assert.match(report.errors[0], /not visible/);
});
