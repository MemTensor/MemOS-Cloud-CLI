import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const releaseWorkflow = readFileSync(new URL("../workflows/release.yml", import.meta.url), "utf8");
const dryRunWorkflow = readFileSync(new URL("../workflows/release-dry-run.yml", import.meta.url), "utf8");

test("CLI reusable dry run is read-only and cannot publish", () => {
  assert.doesNotMatch(releaseWorkflow, /workflow_call:/);
  assert.match(dryRunWorkflow, /workflow_call:/);
  assert.match(dryRunWorkflow, /permissions:\s*\n\s*contents: read/);
  assert.match(dryRunWorkflow, /persist-credentials: false/);
  assert.doesNotMatch(dryRunWorkflow, /NPM_TOKEN/);
  assert.doesNotMatch(dryRunWorkflow, /OSS_ACCESS_KEY/);
  assert.doesNotMatch(dryRunWorkflow, /npm publish/);
  assert.doesNotMatch(dryRunWorkflow, /gh release create/);
  assert.doesNotMatch(dryRunWorkflow, /contents: write/);
  assert.doesNotMatch(dryRunWorkflow, /pull-requests: write/);
});

test("CLI publication persists an immutable source before OSS and npm", () => {
  const durable = releaseWorkflow.indexOf("Push a durable release source before external publication");
  const oss = releaseWorkflow.indexOf("Upload assets to OSS and verify each object");
  const npm = releaseWorkflow.indexOf('npm publish --access public --tag "${NPM_DIST_TAG}"');
  assert.ok(durable >= 0 && durable < oss);
  assert.ok(durable < npm);
  assert.match(releaseWorkflow, /EXPECTED_RELEASE_COMMIT: \$\{\{ needs\.metadata\.outputs\.release_commit_sha \}\}/);
  assert.match(releaseWorkflow, /npm records gitHead/);
  assert.match(releaseWorkflow, /git tag -a "\$\{RELEASE_TAG\}" "\$\{RELEASE_COMMIT_SHA\}"/);
  assert.match(releaseWorkflow, /--target "\$\{RELEASE_COMMIT_SHA\}"/);
});

test("CLI release inventory and create reconciliation fail closed", () => {
  assert.match(releaseWorkflow, /gh api --paginate --slurp/);
  assert.match(releaseWorkflow, /validate-github-release-inventory\.mjs/);
  assert.match(releaseWorkflow, /Refusing to issue a second create request/);
  assert.doesNotMatch(releaseWorkflow, /gh release view/);
});

test("CLI inspection always carries evidence and quality artifacts", () => {
  for (const artifact of [
    "release-notes.md",
    "evidence.json",
    "quality-report.json",
    "docs-preview.md",
    "docs-preview.json",
    "release-assets-manifest.json",
    "npm-pack.json",
  ]) {
    assert.match(dryRunWorkflow, new RegExp(artifact.replaceAll(".", "\\.")));
  }
  assert.match(releaseWorkflow, /if: \$\{\{ always\(\) \}\}/);
  assert.match(releaseWorkflow, /quality_report_file/);
});

test("automatic npm-only binary reconstruction is disabled", () => {
  assert.match(releaseWorkflow, /Automatic npm-only recovery is disabled for CLI binaries/);
  assert.match(releaseWorkflow, /Backfill an audited baseline tag from npm gitHead/);
});
