import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
  chmodSync,
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import test from "node:test";

import {
  PRODUCT_ID,
  buildDocsPreview,
  cleanVersion,
  collectCliEvidence,
  compareSemver,
  composePublicReleaseNotes,
  curateDraftByEvidence,
  docsPreviewMarkdown,
  findPreviousTag,
  generateGitHubReleaseNotes,
  hasSensitiveContent,
  injectDraftFault,
  parseSemver,
  redact,
  reportFailure,
  requestDocAgentDraft,
  reviewedReleaseNotesAtRef,
  sourceRefsFromText,
  validateDocAgentConfiguration,
  validateDraftFirstRelease,
  validateDraft,
  validateFaultCase,
  validateLiveReleaseSource,
  validatePublishConfirmation,
  validateReleaseSourceMode,
  validateReleaseTarget,
  validateReleaseVersionOrder,
  validateVersionSources,
} from "./prepare-cli-release.mjs";

const SCRIPT_PATH = join(
  process.cwd(),
  ".github/scripts/prepare-cli-release.mjs",
);
const PUBLISH_SCRIPT_PATH = join(
  process.cwd(),
  ".github/scripts/publish-cli-release.sh",
);
function fakeGitHubToken() {
  return `ghp_${"a".repeat(36)}`;
}

function fakeBearerCredential() {
  return `Bearer ${fakeGitHubToken()}`;
}

function trustedDispatchEnv(overrides = {}) {
  return {
    ...process.env,
    GITHUB_REF: "refs/heads/main",
    GITHUB_REPOSITORY: "MemTensor/MemOS-Cloud-CLI",
    ...overrides,
  };
}

function git(args) {
  return execFileSync("git", args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function write(path, contents) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, contents, "utf8");
}

function writeVersions(version) {
  write(
    "package.json",
    `${JSON.stringify({ name: "@memtensor/memos-cloud-cli", version }, null, 2)}\n`,
  );
  write(
    "pyproject.toml",
    `[project]\nname = "memos-cli"\nversion = "${version}"\n`,
  );
  write(
    "src/memos_cli/__init__.py",
    `"""MemOS CLI."""\n\n__version__ = "${version}"\n`,
  );
}

function commit(message, body = "") {
  git(["add", "."]);
  const args = ["commit", "-q", "-m", message];
  if (body) args.push("-m", body);
  git(args);
  return git(["rev-parse", "HEAD"]);
}

function withFixture(
  fn,
  {
    baselineVersion = "0.1.0-beta.14",
    baselineTag = `v${baselineVersion}`,
  } = {},
) {
  const previous = process.cwd();
  const root = mkdtempSync(join(tmpdir(), "memos-cli-release-"));
  try {
    process.chdir(root);
    git(["init", "-q"]);
    git(["config", "user.email", "release-test@example.invalid"]);
    git(["config", "user.name", "Release Test"]);
    writeVersions(baselineVersion);
    write("src/memos_cli/main.py", "def app():\n    return 'baseline'\n");
    commit(`chore: synthetic baseline ${baselineVersion}`);
    git(["tag", baselineTag]);
    return fn(root);
  } finally {
    process.chdir(previous);
  }
}

function runPublishFixture({
  remoteMainSha,
  remoteTagSha = "",
  releaseState = "missing",
  initialReleaseDelayed = false,
  recover = "false",
  version = "2.0.0",
  tagVisibilityDelay = 0,
  tagPushStatus = 0,
  tagPushMaterializes = true,
  releaseVisibilityDelay = 0,
  assetVisibilityDelay = 0,
  releaseCreateStatus = 0,
  releaseCreateMaterializes = true,
  uploadFailures = 0,
  editFailures = 0,
  releaseSourceMode = "manual_dispatch",
  npmVersionExists = "false",
  npmGitHead = "",
  liveNpmVersionExists = npmVersionExists,
  liveNpmGitHead = npmGitHead,
} = {}) {
  const root = mkdtempSync(join(tmpdir(), "memos-cli-publish-"));
  const mockBin = join(root, "mock-bin");
  const runnerTemp = join(root, "runner-temp");
  const callLog = join(root, "calls.log");
  const remoteTagState = join(root, "remote-tag-state");
  const remoteTagLookupCount = join(root, "remote-tag-lookup-count");
  const releaseStateFile = join(root, "release-state");
  const releaseLookupCount = join(root, "release-lookup-count");
  const assetsVisibleFile = join(root, "assets-visible");
  const uploadCount = join(root, "upload-count");
  const editCount = join(root, "edit-count");
  const targetSha = "abc1234000000000000000000000000000000000";
  const effectiveRemoteMainSha = remoteMainSha ?? targetSha;
  const currentTag = `v${version}`;
  mkdirSync(mockBin, { recursive: true });
  mkdirSync(runnerTemp, { recursive: true });
  write(
    join(root, "release-inspection/github-release-notes.md"),
    "# What's Changed\n\n- Verified release note.\n",
  );
  write(join(root, "dist/memos-test.tar.gz"), "test archive");
  if (initialReleaseDelayed && releaseState !== "missing") {
    write(releaseStateFile, `${releaseState}\n`);
    write(releaseLookupCount, "0\n");
  }
  const gitMock = join(mockBin, "git");
  write(
    gitMock,
    [
      "#!/usr/bin/env bash",
      "set -euo pipefail",
      "printf 'git %s\\n' \"$*\" >> \"${CALL_LOG}\"",
      "if [[ \"${1:-}\" == \"ls-remote\" && \"${2:-}\" == \"origin\" && \"${3:-}\" == \"refs/heads/main\" ]]; then",
      "  if [[ -n \"${MOCK_REMOTE_MAIN_SHA:-}\" ]]; then",
      "    printf '%s\\trefs/heads/main\\n' \"${MOCK_REMOTE_MAIN_SHA}\"",
      "  fi",
      "elif [[ \"${1:-}\" == \"ls-remote\" && \"${2:-}\" == \"--tags\" ]]; then",
      "  tag_sha=\"${MOCK_REMOTE_TAG_SHA:-}\"",
      "  if [[ -s \"${MOCK_REMOTE_TAG_STATE}\" ]]; then",
      "    lookup_count=0",
      "    if [[ -s \"${MOCK_REMOTE_TAG_LOOKUP_COUNT}\" ]]; then lookup_count=$(<\"${MOCK_REMOTE_TAG_LOOKUP_COUNT}\"); fi",
      "    lookup_count=$((lookup_count + 1))",
      "    printf '%s\\n' \"${lookup_count}\" > \"${MOCK_REMOTE_TAG_LOOKUP_COUNT}\"",
      "    if [[ \"${lookup_count}\" -gt \"${MOCK_TAG_VISIBILITY_DELAY}\" ]]; then tag_sha=$(<\"${MOCK_REMOTE_TAG_STATE}\"); else tag_sha=''; fi",
      "  fi",
      "  if [[ -n \"${tag_sha}\" ]]; then printf '%s\\trefs/tags/%s\\n' \"${tag_sha}\" \"${CURRENT_TAG}\"; fi",
      "elif [[ \"${1:-}\" == \"push\" && \"${2:-}\" == \"origin\" ]]; then",
      "  if [[ \"${MOCK_TAG_PUSH_MATERIALIZES}\" == \"true\" ]]; then printf '%s\\n' \"${TARGET_SHA}\" > \"${MOCK_REMOTE_TAG_STATE}\"; fi",
      "  exit \"${MOCK_TAG_PUSH_STATUS}\"",
      "fi",
      "",
    ].join("\n"),
  );
  chmodSync(gitMock, 0o755);
  const npmMock = join(mockBin, "npm");
  write(
    npmMock,
    [
      "#!/usr/bin/env bash",
      "set -euo pipefail",
      "printf 'npm %s\\n' \"$*\" >> \"${CALL_LOG}\"",
      "if [[ \"${MOCK_LIVE_NPM_VERSION_EXISTS}\" == \"true\" ]]; then",
      "  printf '{\"version\":\"%s\",\"gitHead\":\"%s\"}\\n' \"${RELEASE_VERSION}\" \"${MOCK_LIVE_NPM_GIT_HEAD}\"",
      "  exit 0",
      "fi",
      "echo 'npm error code E404' >&2",
      "exit 1",
      "",
    ].join("\n"),
  );
  chmodSync(npmMock, 0o755);
  const ghMock = join(mockBin, "gh");
  write(
    ghMock,
    [
      "#!/usr/bin/env bash",
      "set -euo pipefail",
      "printf 'gh %s\\n' \"$*\" >> \"${CALL_LOG}\"",
      "if [[ \"${1:-}\" == \"release\" && \"${2:-}\" == \"view\" ]]; then",
      "  current_state=\"${MOCK_RELEASE_STATE}\"",
      "  asset_names='memos-test.tar.gz'",
      "  if [[ -s \"${MOCK_RELEASE_STATE_FILE}\" ]]; then",
      "    lookup_count=0",
      "    if [[ -s \"${MOCK_RELEASE_LOOKUP_COUNT}\" ]]; then lookup_count=$(<\"${MOCK_RELEASE_LOOKUP_COUNT}\"); fi",
      "    lookup_count=$((lookup_count + 1))",
      "    printf '%s\\n' \"${lookup_count}\" > \"${MOCK_RELEASE_LOOKUP_COUNT}\"",
      "    if [[ \"${lookup_count}\" -gt \"${MOCK_RELEASE_VISIBILITY_DELAY}\" ]]; then current_state=$(<\"${MOCK_RELEASE_STATE_FILE}\"); else current_state='missing'; fi",
      "    asset_visible_after=$((MOCK_RELEASE_VISIBILITY_DELAY + MOCK_ASSET_VISIBILITY_DELAY))",
      "    if [[ \"${lookup_count}\" -le \"${asset_visible_after}\" && ! -e \"${MOCK_ASSETS_VISIBLE_FILE}\" ]]; then asset_names=''; fi",
      "  fi",
      "  case \"${current_state}\" in",
      "    missing)",
      "      echo 'release not found' >&2",
      "      exit 1",
      "      ;;",
      "    draft)",
      "      printf 'true\\tfalse\\thttps://example.invalid/draft\\t%s\\n' \"${asset_names}\"",
      "      ;;",
      "    prerelease-draft)",
      "      printf 'true\\ttrue\\thttps://example.invalid/draft\\t%s\\n' \"${asset_names}\"",
      "      ;;",
      "    published)",
      "      printf 'false\\tfalse\\thttps://example.invalid/published\\t%s\\n' \"${asset_names}\"",
      "      ;;",
      "    *)",
      "      echo 'unexpected mock release state' >&2",
      "      exit 2",
      "      ;;",
      "  esac",
      "elif [[ \"${1:-}\" == \"release\" && \"${2:-}\" == \"create\" ]]; then",
      "  if [[ \"${MOCK_RELEASE_CREATE_MATERIALIZES}\" == \"true\" ]]; then",
      "    created_state='draft'",
      "    if [[ \" $* \" == *' --prerelease '* ]]; then created_state='prerelease-draft'; fi",
      "    printf '%s\\n' \"${created_state}\" > \"${MOCK_RELEASE_STATE_FILE}\"",
      "    printf '0\\n' > \"${MOCK_RELEASE_LOOKUP_COUNT}\"",
      "  fi",
      "  exit \"${MOCK_RELEASE_CREATE_STATUS}\"",
      "elif [[ \"${1:-}\" == \"release\" && \"${2:-}\" == \"upload\" ]]; then",
      "  count=0; if [[ -s \"${MOCK_UPLOAD_COUNT}\" ]]; then count=$(<\"${MOCK_UPLOAD_COUNT}\"); fi; count=$((count + 1)); printf '%s\\n' \"${count}\" > \"${MOCK_UPLOAD_COUNT}\"",
      "  if [[ \"${count}\" -le \"${MOCK_UPLOAD_FAILURES}\" ]]; then echo 'temporary upload failure' >&2; exit 1; fi",
      "  : > \"${MOCK_ASSETS_VISIBLE_FILE}\"",
      "elif [[ \"${1:-}\" == \"release\" && \"${2:-}\" == \"edit\" ]]; then",
      "  count=0; if [[ -s \"${MOCK_EDIT_COUNT}\" ]]; then count=$(<\"${MOCK_EDIT_COUNT}\"); fi; count=$((count + 1)); printf '%s\\n' \"${count}\" > \"${MOCK_EDIT_COUNT}\"",
      "  if [[ \"${count}\" -le \"${MOCK_EDIT_FAILURES}\" ]]; then echo 'temporary edit failure' >&2; exit 1; fi",
      "fi",
      "",
    ].join("\n"),
  );
  chmodSync(ghMock, 0o755);
  let output = "";
  let failure;
  try {
    output = execFileSync("bash", [PUBLISH_SCRIPT_PATH], {
      cwd: root,
      encoding: "utf8",
      env: {
        ...process.env,
        PATH: `${mockBin}:${dirname(process.execPath)}:/usr/bin:/bin`,
        CALL_LOG: callLog,
        MOCK_REMOTE_MAIN_SHA: effectiveRemoteMainSha,
        MOCK_REMOTE_TAG_SHA: remoteTagSha,
        MOCK_REMOTE_TAG_STATE: remoteTagState,
        MOCK_REMOTE_TAG_LOOKUP_COUNT: remoteTagLookupCount,
        MOCK_TAG_VISIBILITY_DELAY: String(tagVisibilityDelay),
        MOCK_TAG_PUSH_STATUS: String(tagPushStatus),
        MOCK_TAG_PUSH_MATERIALIZES: String(tagPushMaterializes),
        MOCK_RELEASE_STATE: releaseState,
        MOCK_RELEASE_STATE_FILE: releaseStateFile,
        MOCK_RELEASE_LOOKUP_COUNT: releaseLookupCount,
        MOCK_ASSETS_VISIBLE_FILE: assetsVisibleFile,
        MOCK_RELEASE_VISIBILITY_DELAY: String(releaseVisibilityDelay),
        MOCK_ASSET_VISIBILITY_DELAY: String(assetVisibilityDelay),
        MOCK_RELEASE_CREATE_STATUS: String(releaseCreateStatus),
        MOCK_RELEASE_CREATE_MATERIALIZES: String(releaseCreateMaterializes),
        MOCK_UPLOAD_COUNT: uploadCount,
        MOCK_UPLOAD_FAILURES: String(uploadFailures),
        MOCK_EDIT_COUNT: editCount,
        MOCK_EDIT_FAILURES: String(editFailures),
        RELEASE_RETRY_ATTEMPTS: "4",
        RELEASE_RETRY_SLEEP_SECONDS: "0",
        CURRENT_TAG: currentTag,
        TARGET_SHA: targetSha,
        RECOVER_EXISTING_RELEASE: recover,
        RELEASE_VERSION: version,
        RELEASE_SOURCE_MODE: releaseSourceMode,
        NPM_VERSION_EXISTS: npmVersionExists,
        NPM_GIT_HEAD: npmGitHead,
        MOCK_LIVE_NPM_VERSION_EXISTS: liveNpmVersionExists,
        MOCK_LIVE_NPM_GIT_HEAD: liveNpmGitHead,
        GITHUB_REPOSITORY: "MemTensor/MemOS-Cloud-CLI",
        RUNNER_TEMP: runnerTemp,
        GH_TOKEN: "test-token",
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    failure = error;
    output = `${String(error.stdout || "")}${String(error.stderr || "")}`;
  }
  return {
    callLog: readFileSync(callLog, "utf8"),
    currentTag,
    failure,
    output,
    targetSha,
  };
}

const evidence = {
  commits: [
    {
      sha: "abc1234000000000000000000000000000000000",
      short_sha: "abc1234",
      subject: "fix: explain authentication failures (#31)",
      source_refs: [
        "abc1234",
        "abc1234000000000000000000000000000000000",
        "#31",
      ],
    },
  ],
  pull_requests: [{ number: "31" }],
  important_commits: [
    {
      sha: "abc1234000000000000000000000000000000000",
      short_sha: "abc1234",
      subject: "fix: explain authentication failures (#31)",
    },
  ],
  required_source_refs: [
    {
      short_sha: "abc1234",
      accepted_refs: [
        "abc1234",
        "abc1234000000000000000000000000000000000",
        "#31",
      ],
    },
  ],
  has_user_facing_product_changes: true,
  repo: "MemTensor/MemOS-Cloud-CLI",
  previous_tag: "v0.1.0-beta.14",
  current_tag: "v1.0.7",
  target_version: "v1.0.7",
  git_ref: "def5678",
};

const validDraft = {
  ok: true,
  needs_review: false,
  confidence: "high",
  warnings: [],
  release_items: [
    {
      category: "Fixed",
      text_cn:
        "**登录错误提示**：登录失败时展示更明确的认证原因，便于快速修正配置。",
      text_en:
        "**Authentication errors**: Shows a clearer cause after sign-in failures so configuration can be corrected quickly.",
      source_refs: ["abc1234", "#31"],
    },
  ],
};

test("uses SemVer precedence instead of lexical ordering", () => {
  assert.ok(compareSemver("1.0.0-beta.10", "1.0.0-beta.9") > 0);
  assert.ok(compareSemver("1.0.0", "1.0.0-beta.20") > 0);
  assert.equal(compareSemver("1.0.0+build.2", "1.0.0+build.1"), 0);
  assert.equal(
    findPreviousTag("1.0.7", "v1.0.7", [
      "v0.1.0-beta.14",
      "v1.0.7-beta.1",
      "v1.0.7",
      "not-a-release",
    ]),
    "v0.1.0-beta.14",
  );
  assert.equal(
    findPreviousTag("1.0.7-beta.10", "v1.0.7-beta.10", [
      "v0.1.0-beta.14",
      "v1.0.7-beta.9",
      "v1.0.7-beta.2",
    ]),
    "v1.0.7-beta.9",
  );
  assert.equal(parseSemver("1.0.07"), null);
  assert.equal(parseSemver("1.0.7-beta.01"), null);
  assert.ok(
    compareSemver(
      "1.0.7-beta.100000000000000000000",
      "1.0.7-beta.99999999999999999999",
    ) > 0,
  );
});

test("refuses an out-of-order version before creating a new release tag", () => {
  assert.equal(
    validateReleaseVersionOrder("1.0.8", "v1.0.8", ["v1.0.6", "v1.0.7"]),
    "v1.0.7",
  );
  assert.throws(
    () =>
      validateReleaseVersionOrder("1.0.7", "v1.0.7", [
        "v1.0.6",
        "v1.0.8-beta.1",
      ]),
    /newer than the latest existing SemVer tag/,
  );
});

test("requires version without v and an exact live confirmation", () => {
  assert.equal(cleanVersion("1.0.7"), "1.0.7");
  assert.throws(() => cleanVersion("v1.0.7"), /leading v/);
  assert.doesNotThrow(() =>
    validatePublishConfirmation({
      dryRun: "true",
      version: "1.0.7",
      confirmation: "",
    }),
  );
  assert.doesNotThrow(() =>
    validatePublishConfirmation({
      dryRun: "false",
      version: "1.0.7",
      confirmation: "",
      releaseSourceMode: "trusted_main_push",
    }),
  );
  assert.equal(validateReleaseSourceMode("manual_dispatch"), "manual_dispatch");
  assert.throws(
    () => validateReleaseSourceMode("untrusted_auto"),
    /unknown release source mode/,
  );
  assert.throws(
    () =>
      validatePublishConfirmation({
        dryRun: "false",
        version: "1.0.7",
        confirmation: "",
      }),
    /PUBLISH v1\.0\.7/,
  );
  assert.doesNotThrow(() =>
    validatePublishConfirmation({
      dryRun: "false",
      version: "1.0.7",
      confirmation: "PUBLISH v1.0.7",
    }),
  );
});

test("requires every live run to create a Draft Release for manual review", () => {
  assert.doesNotThrow(() =>
    validateDraftFirstRelease({
      dryRun: "true",
      createDraftRelease: "false",
    }),
  );
  assert.doesNotThrow(() =>
    validateDraftFirstRelease({
      dryRun: "false",
      createDraftRelease: "true",
    }),
  );
  assert.throws(
    () =>
      validateDraftFirstRelease({
        dryRun: "false",
        createDraftRelease: "false",
      }),
    /requires create_draft_release=true/,
  );
});

test("allows non-main target refs only for dry runs", () => {
  assert.doesNotThrow(() =>
    validateReleaseTarget({ dryRun: "true", targetRef: "feature/preview" }),
  );
  assert.doesNotThrow(() =>
    validateReleaseTarget({ dryRun: "false", targetRef: "main" }),
  );
  assert.throws(
    () =>
      validateReleaseTarget({
        dryRun: "false",
        targetRef: "feature/preview",
      }),
    /exactly main/,
  );
  assert.doesNotThrow(() =>
    validateReleaseTarget({
      dryRun: "false",
      targetRef: "a".repeat(40),
      releaseSourceMode: "trusted_main_push",
    }),
  );
  assert.throws(
    () =>
      validateReleaseTarget({
        dryRun: "false",
        targetRef: "not-an-after-sha",
        releaseSourceMode: "trusted_main_push",
      }),
    /after commit SHA/,
  );
});

test("runs trusted workflow code from the default branch and restricts live targets", () => {
  assert.throws(
    () =>
      validateLiveReleaseSource({
        dryRun: "true",
        workflowRef: "refs/heads/feature/preview",
        defaultBranch: "main",
        targetSha: "aaa",
        defaultBranchSha: "bbb",
      }),
    /must be dispatched from the protected default branch/,
  );
  assert.doesNotThrow(() =>
    validateLiveReleaseSource({
      dryRun: "true",
      workflowRef: "refs/heads/main",
      defaultBranch: "main",
      targetSha: "aaa",
      defaultBranchSha: "bbb",
    }),
  );
  assert.doesNotThrow(() =>
    validateLiveReleaseSource({
      dryRun: "false",
      workflowRef: "refs/heads/main",
      defaultBranch: "main",
      targetSha: "aaa",
      defaultBranchSha: "aaa",
    }),
  );
  assert.throws(
    () =>
      validateLiveReleaseSource({
        dryRun: "false",
        workflowRef: "refs/heads/feature/release",
        defaultBranch: "main",
        targetSha: "aaa",
        defaultBranchSha: "aaa",
      }),
    /must be dispatched from the protected default branch/,
  );
  assert.throws(
    () =>
      validateLiveReleaseSource({
        dryRun: "false",
        workflowRef: "refs/heads/main",
        defaultBranch: "main",
        targetSha: "aaa",
        defaultBranchSha: "bbb",
      }),
    /stale or non-default commit/,
  );
  assert.doesNotThrow(() =>
    validateLiveReleaseSource({
      dryRun: "false",
      workflowRef: "refs/pull/123/merge",
      defaultBranch: "main",
      targetSha: "aaa",
      defaultBranchSha: "bbb",
      targetIsDefaultBranchAncestor: true,
      releaseSourceMode: "trusted_main_push",
    }),
  );
  assert.throws(
    () =>
      validateLiveReleaseSource({
        dryRun: "false",
        workflowRef: "refs/heads/main",
        defaultBranch: "main",
        targetSha: "aaa",
        defaultBranchSha: "bbb",
        targetIsDefaultBranchAncestor: false,
        releaseSourceMode: "trusted_main_push",
      }),
    /contained in origin\/main/,
  );
});

test("preflights all Doc Agent secret names without exposing their values", () => {
  assert.doesNotThrow(() =>
    validateDocAgentConfiguration({
      env: {
        DOC_AGENT_RELEASE_NOTES_DRAFT_URL:
          "https://example.invalid/release-notes",
        DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN: "not-logged",
        DOC_AGENT_RELEASE_FAILURE_URL: "https://example.invalid/failure",
      },
    }),
  );
  assert.throws(
    () =>
      validateDocAgentConfiguration({
        env: {
          DOC_AGENT_RELEASE_NOTES_DRAFT_URL:
            "https://example.invalid/release-notes",
          DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN: "not-logged",
        },
      }),
    /DOC_AGENT_RELEASE_FAILURE_URL/,
  );
  assert.throws(
    () =>
      validateDocAgentConfiguration({
        env: {
          DOC_AGENT_RELEASE_NOTES_DRAFT_URL: "file:///tmp/draft",
          DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN: "not-logged",
          DOC_AGENT_RELEASE_FAILURE_URL: "https://example.invalid/failure",
        },
      }),
    /HTTP\(S\) URL/,
  );
  assert.doesNotThrow(
    () =>
      validateDocAgentConfiguration({
        env: {
          DOC_AGENT_RELEASE_NOTES_DRAFT_URL:
            "http://example.invalid/release-notes",
          DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN: "not-logged",
          DOC_AGENT_RELEASE_FAILURE_URL: "http://example.invalid/failure",
        },
      }),
  );
  assert.throws(
    () =>
      validateDocAgentConfiguration({
        env: {
          DOC_AGENT_RELEASE_NOTES_DRAFT_URL:
            "https://draft.example.invalid/release-notes",
          DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN: "not-logged",
          DOC_AGENT_RELEASE_FAILURE_URL:
            "https://failure.example.invalid/failure",
        },
      }),
    /same origin/,
  );
});

test("allows fault injection only in dry runs", () => {
  assert.equal(
    validateFaultCase({ dryRun: "true", faultCase: "mixed_language" }),
    "mixed_language",
  );
  assert.throws(
    () =>
      validateFaultCase({
        dryRun: "false",
        faultCase: "missing_source_refs",
      }),
    /only allowed when dry_run=true/,
  );
  assert.throws(
    () =>
      validateFaultCase({ dryRun: "true", faultCase: "unknown_fault" }),
    /unknown release fault case/,
  );
});

test("requires all three CLI version sources to match", () => {
  assert.doesNotThrow(() =>
    validateVersionSources("1.0.7", {
      package_json: "1.0.7",
      pyproject_toml: "1.0.7",
      python_init: "1.0.7",
    }),
  );
  assert.throws(
    () =>
      validateVersionSources("1.0.7", {
        package_json: "1.0.7",
        pyproject_toml: "0.1.0-beta.14",
        python_init: "1.0.7",
      }),
    /pyproject_toml=1\.0\.6/,
  );
});

test("extracts PR references from common commit and GitHub wording", () => {
  assert.deepEqual(
    sourceRefsFromText(
      "fix: auth failure (#31)\nFixes #32\nhttps://github.com/MemTensor/MemOS-Cloud-CLI/pull/33",
    ),
    ["#31", "#32", "#33"],
  );
});

test("collects the entire standalone CLI repository but filters release noise", () => {
  withFixture(() => {
    write("src/memos_cli/auth.py", "def explain_error():\n    return 'expired'\n");
    const featureSha = commit("Fix memory API endpoint paths (#31)");
    write(
      ".github/workflows/noise.yml",
      "name: noise\non: workflow_dispatch\n",
    );
    commit("ci: tune release workflow");
    writeVersions("1.0.7");
    commit("feat: modify version to 1.0.7");

    const result = collectCliEvidence({
      previousTag: "v0.1.0-beta.14",
      currentTag: "v1.0.7",
      currentRef: "HEAD",
      targetVersion: "1.0.7",
      repo: "MemTensor/MemOS-Cloud-CLI",
    });

    assert.equal(result.product_id, PRODUCT_ID);
    assert.equal(result.evidence_scope, "whole_repository");
    assert.deepEqual(result.product_paths, ["**"]);
    assert.ok(
      result.changed_files.some((item) => item.path === "src/memos_cli/auth.py"),
    );
    assert.ok(
      result.changed_files.some(
        (item) => item.path === ".github/workflows/noise.yml",
      ),
    );
    assert.deepEqual(
      result.important_commits.map((item) => item.sha),
      [featureSha],
    );
    assert.equal(result.required_source_refs.length, 1);
    assert.ok(result.required_source_refs[0].accepted_refs.includes("#31"));
    assert.equal(result.package_changes.length, 3);
    assert.equal(
      result.release_context.docs_product_extraction,
      "whole_tag_range_after_release_published",
    );
  });
});

test("does not publish a docs item for automation-only changes", () => {
  withFixture(() => {
    write(".github/workflows/release.yml", "name: release\n");
    commit("ci: improve changelog validation");
    const result = collectCliEvidence({
      previousTag: "v0.1.0-beta.14",
      currentTag: "v1.0.7",
      currentRef: "HEAD",
      targetVersion: "1.0.7",
      repo: "MemTensor/MemOS-Cloud-CLI",
    });
    assert.equal(result.has_product_changes, true);
    assert.equal(result.has_user_facing_product_changes, false);
    assert.match(result.skip_reason, /no user-facing/);
  });
});

test("does not treat fix-scoped CI or workflow-only changes as CLI features", () => {
  withFixture(() => {
    write(".github/workflows/release.yml", "name: hardened release\n");
    commit("fix(ci): harden release workflow");
    const result = collectCliEvidence({
      previousTag: "v0.1.0-beta.14",
      currentTag: "v1.0.7",
      currentRef: "HEAD",
      targetVersion: "1.0.7",
      repo: "MemTensor/MemOS-Cloud-CLI",
    });
    assert.equal(result.has_product_changes, true);
    assert.equal(result.has_user_facing_product_changes, false);
    assert.equal(result.important_commits.length, 0);
  });
});

test("does not announce a feature that was fully reverted in the same range", () => {
  withFixture(() => {
    write("src/memos_cli/temporary.py", "ENABLED = True\n");
    const featureSha = commit("feat: add temporary CLI mode (#41)");
    git(["revert", "--no-edit", featureSha]);
    const result = collectCliEvidence({
      previousTag: "v0.1.0-beta.14",
      currentTag: "v1.0.7",
      currentRef: "HEAD",
      targetVersion: "1.0.7",
      repo: "MemTensor/MemOS-Cloud-CLI",
    });
    assert.equal(result.changed_files.length, 0);
    assert.equal(result.important_commits.length, 0);
    assert.equal(result.has_user_facing_product_changes, false);
  });
});

test("uses an optional reviewed version note and otherwise composes the validated Doc Agent draft", () => {
  withFixture(() => {
    write(
      ".github/release-notes/v1.0.7.md",
      "## Highlights\n\n- Authentication failures now explain the recovery step.\n",
    );
    const targetSha = commit("docs: add reviewed v1.0.7 release note");
    const reviewed = reviewedReleaseNotesAtRef({
      targetSha,
      currentTag: "v1.0.7",
    });
    assert.equal(reviewed.path, ".github/release-notes/v1.0.7.md");
    const manual = composePublicReleaseNotes({
      githubNotes: {
        name: "MemOS CLI v1.0.7",
        body: "## What's Changed\n\n* Fix authentication errors.",
      },
      draft: validDraft,
      reviewedNotes: reviewed,
    });
    assert.equal(manual.source, "reviewed-file-plus-github-whats-changed");
    assert.match(manual.body, /Authentication failures/);
    assert.match(manual.body, /What's Changed/);

    const generated = composePublicReleaseNotes({
      githubNotes: {
        name: "MemOS CLI v1.0.7",
        body: "## What's Changed\n\n* Fix authentication errors.",
      },
      draft: validDraft,
    });
    assert.equal(
      generated.source,
      "validated-doc-agent-plus-github-whats-changed",
    );
    assert.match(generated.body, /## Changelog/);
    assert.match(generated.body, /Authentication errors/);
  });
});

test("rejects placeholder or sensitive reviewed Release notes", () => {
  withFixture(() => {
    write(
      ".github/release-notes/v1.0.7.md",
      "## Highlights\n\n- TODO replace this draft before release.\n",
    );
    const placeholderSha = commit("docs: add placeholder release note");
    assert.throws(
      () =>
        reviewedReleaseNotesAtRef({
          targetSha: placeholderSha,
          currentTag: "v1.0.7",
        }),
      /TODO\/TBD\/PLACEHOLDER/,
    );

    write(
      ".github/release-notes/v1.0.8.md",
      `## Highlights\n\n- Contact https://${["10", "0", "0", "8"].join(".")}/internal/release for rollout details.\n`,
    );
    const sensitiveSha = commit("docs: add unsafe release note");
    assert.throws(
      () =>
        reviewedReleaseNotesAtRef({
          targetSha: sensitiveSha,
          currentTag: "v1.0.8",
        }),
      /credential-like or internal content/,
    );
  });
});

test("runs an end-to-end offline dry run and writes the inspection contract", () => {
  withFixture((root) => {
    writeVersions("99.99.99");
    write(
      "src/memos_cli/auth.py",
      "def explain_error():\n    return 'credential expired'\n",
    );
    commit("fix(auth): explain expired credentials (#31)");
    const runnerTemp = join(root, "runner-temp");
    execFileSync("node", [SCRIPT_PATH], {
      encoding: "utf8",
      env: trustedDispatchEnv({
        RELEASE_VERSION: "99.99.99",
        TARGET_REF: "HEAD",
        DRY_RUN: "true",
        ALLOW_OFFLINE_DOCS_PREVIEW: "true",
        RELEASE_CONTRACT_FIXTURE: "true",
        RUNNER_TEMP: runnerTemp,
        GITHUB_TOKEN: "",
      }),
      stdio: ["ignore", "pipe", "pipe"],
    });
    const inspection = join(
      runnerTemp,
      "memos-cloud-cli-release-inspection",
    );
    for (const name of [
      "README.md",
      "github-release-notes.md",
      "release-notes.md",
      "release-notes-source.json",
      "evidence.json",
      "release-notes-draft.json",
      "docs-preview.md",
      "docs-preview.json",
      "quality-report.json",
      "release-contract.json",
    ]) {
      assert.equal(existsSync(join(inspection, name)), true, name);
    }
    const report = JSON.parse(
      readFileSync(join(inspection, "quality-report.json"), "utf8"),
    );
    assert.equal(report.ok, true);
    assert.equal(report.previous_tag, "v99.99.98");
    assert.equal(report.current_tag, "v99.99.99");
    assert.equal(report.inspection_kind, "synthetic_contract_fixture");
    assert.equal(report.publish_blocked, false);
    assert.equal(report.existing_tag_status, "absent");
    assert.equal(
      report.release_notes_source,
      "validated-doc-agent-plus-github-whats-changed",
    );
    assert.deepEqual(report.product_paths, ["**"]);
    assert.equal(report.coverage.missing_required_count, 0);
    assert.equal(report.evidence_curation.removed_item_count, 0);
    const evidence = JSON.parse(
      readFileSync(join(inspection, "evidence.json"), "utf8"),
    );
    assert.deepEqual(evidence.product_paths, ["**"]);
    const acceptedDraft = JSON.parse(
      readFileSync(join(inspection, "release-notes-draft.json"), "utf8"),
    );
    assert.equal(acceptedDraft.ok, true);
    assert.equal(acceptedDraft.evidence_curation.removed_item_count, 0);
    assert.ok(acceptedDraft.release_items[0].source_refs.length > 0);
    assert.match(
      readFileSync(join(inspection, "README.md"), "utf8"),
      /inspection_kind: synthetic_contract_fixture[\s\S]*coverage_missing_required_count: 0/,
    );
    const contract = JSON.parse(
      readFileSync(join(inspection, "release-contract.json"), "utf8"),
    );
    assert.equal(contract.release_trigger, "release.published");
    assert.equal(contract.required_webhook_event, "release");
    assert.equal(
      contract.draft_release_trigger,
      "official main push after an internal or fork PR merge with an all-three-file SemVer increase, or manual workflow_dispatch",
    );
    assert.deepEqual(contract.product_paths, ["**"]);
    assert.equal(
      contract.live_release_policy.default_entry,
      "automatic official main push with an all-three-file SemVer increase",
    );
    assert.equal(contract.live_release_policy.creates_draft_release, true);
    assert.equal(contract.live_release_policy.direct_publish_allowed, false);
    assert.equal(contract.reviewed_release_notes_optional, true);
    assert.deepEqual(contract.dry_run_side_effects, {
      creates_tag: false,
      creates_github_release: false,
      creates_docs_pr: false,
      deploys_pre: false,
      deploys_gray: false,
      deploys_production: false,
    });
    const exportDir = String(
      process.env.RELEASE_TEST_EXPORT_DIR || "",
    ).trim();
    if (exportDir) {
      cpSync(inspection, exportDir, { recursive: true });
    }
  }, {
    baselineVersion: "99.99.98",
  });
});

test("prepares an automatic Draft from the trusted main push even after main advances", () => {
  withFixture((root) => {
    git(["branch", "-M", "main"]);
    writeVersions("99.99.99");
    write(
      "src/memos_cli/auth.py",
      "def explain_error():\n    return 'credential expired'\n",
    );
    const releaseMergeSha = commit("fix(auth): explain expired credentials (#31)");
    write(".github/workflows/noise.yml", "name: later trusted main check\n");
    commit("ci: later main-only automation update");
    git(["update-ref", "refs/remotes/origin/main", "HEAD"]);

    const runnerTemp = join(root, "runner-temp");
    execFileSync("node", [SCRIPT_PATH], {
      encoding: "utf8",
      env: trustedDispatchEnv({
        RELEASE_VERSION: "99.99.99",
        TARGET_REF: releaseMergeSha,
        DRY_RUN: "false",
        CREATE_DRAFT_RELEASE: "true",
        PUBLISH_CONFIRMATION: "",
        RELEASE_SOURCE_MODE: "trusted_main_push",
        ALLOW_OFFLINE_DOCS_PREVIEW: "true",
        RELEASE_CONTRACT_FIXTURE: "true",
        RUNNER_TEMP: runnerTemp,
        GITHUB_TOKEN: "",
      }),
      stdio: ["ignore", "pipe", "pipe"],
    });
    const inspection = join(runnerTemp, "memos-cloud-cli-release-inspection");
    const report = JSON.parse(
      readFileSync(join(inspection, "quality-report.json"), "utf8"),
    );
    assert.equal(report.ok, true);
    assert.equal(report.release_source_mode, "trusted_main_push");
    assert.equal(report.target_sha, releaseMergeSha);
  }, {
    baselineVersion: "99.99.98",
  });
});

test("records a conflicting existing tag and fails closed", () => {
  withFixture((root) => {
    git(["tag", "v1.0.7", "v0.1.0-beta.14"]);
    writeVersions("1.0.7");
    write("src/memos_cli/auth.py", "def login():\n    return 'improved'\n");
    commit("fix(auth): explain credential failures (#31)");
    const runnerTemp = join(root, "runner-temp");
    assert.throws(() =>
      execFileSync("node", [SCRIPT_PATH], {
        encoding: "utf8",
        env: trustedDispatchEnv({
          RELEASE_VERSION: "1.0.7",
          TARGET_REF: "HEAD",
          DRY_RUN: "true",
          ALLOW_OFFLINE_DOCS_PREVIEW: "true",
          RUNNER_TEMP: runnerTemp,
        }),
        stdio: ["ignore", "pipe", "pipe"],
      }),
    );
    const report = JSON.parse(
      readFileSync(
        join(
          runnerTemp,
          "memos-cloud-cli-release-inspection",
          "quality-report.json",
        ),
        "utf8",
      ),
    );
    assert.equal(report.ok, false);
    assert.equal(report.publish_blocked, true);
    assert.equal(report.existing_tag_status, "conflicts_target");
    assert.match(report.publish_block_reason, /already points to/);
  });
});

test("writes a redacted inspection artifact when preparation fails closed", () => {
  withFixture((root) => {
    const runnerTemp = join(root, "runner-temp");
    let failure;
    try {
      execFileSync("node", [SCRIPT_PATH], {
        encoding: "utf8",
        env: trustedDispatchEnv({
          RELEASE_VERSION: "1.0.7",
          TARGET_REF: "HEAD",
          DRY_RUN: "true",
          ALLOW_OFFLINE_DOCS_PREVIEW: "true",
          RUNNER_TEMP: runnerTemp,
        }),
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch (error) {
      failure = error;
    }
    assert.ok(failure);
    assert.match(
      String(failure.stderr),
      /target_ref version files must all equal 1\.0\.7/,
    );
    const inspection = join(
      runnerTemp,
      "memos-cloud-cli-release-inspection",
    );
    for (const name of [
      "README.md",
      "github-release-notes.md",
      "release-notes.md",
      "evidence.json",
      "release-notes-draft.json",
      "docs-preview.md",
      "docs-preview.json",
      "quality-report.json",
      "release-contract.json",
    ]) {
      assert.equal(existsSync(join(inspection, name)), true, name);
    }
    const report = JSON.parse(
      readFileSync(join(inspection, "quality-report.json"), "utf8"),
    );
    assert.equal(report.ok, false);
    assert.equal(report.needs_review, true);
    assert.equal(report.publish_blocked, true);
    assert.equal(report.phase, "resolve-release-source");
  });
});

test("accepts bilingual concise items with real source refs", () => {
  const result = validateDraft(validDraft, evidence);
  assert.equal(result.ok, true);
  assert.equal(result.coverage.required_count, 1);
  assert.equal(result.coverage.missing_required_count, 0);

  const aliasResult = validateDraft(
    {
      ...validDraft,
      release_items: [
        {
          ...validDraft.release_items[0],
          source_refs: ["abc12340"],
        },
      ],
    },
    evidence,
  );
  assert.equal(aliasResult.ok, true);
  assert.equal(aliasResult.coverage.missing_required_count, 0);
});

test("requests three independent candidates and deterministically selects the valid one", async () => {
  const previousFetch = globalThis.fetch;
  const previousUrl = process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL;
  const previousToken = process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN;
  const requests = [];
  const responses = [
    {
      ok: true,
      needs_review: false,
      release_items: [
        {
          ...validDraft.release_items[0],
          source_refs: ["not-real"],
        },
      ],
    },
    validDraft,
    {
      ok: true,
      needs_review: false,
      release_items: [
        {
          ...validDraft.release_items[0],
          text_en: "登录失败。",
        },
      ],
    },
  ];
  try {
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL =
      "https://example.invalid/draft";
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN = "test-token";
    globalThis.fetch = async (_url, options) => {
      requests.push(JSON.parse(options.body));
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify(responses.shift()),
      };
    };
    const result = await requestDocAgentDraft(evidence);
    assert.equal(result.validation_report.ok, true);
    assert.equal(result.candidate_selection.requested_candidate_count, 3);
    assert.equal(result.candidate_selection.received_candidate_count, 3);
    assert.equal(result.candidate_selection.selected_candidate, 2);
    assert.equal(result.repair_attempt_count, 0);
    assert.equal(requests.length, 3);
    assert.deepEqual(
      requests.map(
        (request) =>
          request.candidate_selection_context.candidate_index,
      ),
      [1, 2, 3],
    );
  } finally {
    globalThis.fetch = previousFetch;
    if (previousUrl === undefined) {
      delete process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL;
    } else {
      process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL = previousUrl;
    }
    if (previousToken === undefined) {
      delete process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN;
    } else {
      process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN = previousToken;
    }
  }
});

test("accepts the real run shape after pruning an extra automation-only item", async () => {
  const previousFetch = globalThis.fetch;
  const previousUrl = process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL;
  const previousToken = process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN;
  const productSha = "a6199ed6c338f8369bf5fccef26c883701ae58bb";
  const automationSha = "9c57e9c60a7cdc3b0ce23de75f1c7a7307138c0d";
  const mergeSha = "cd568a3945fc9d97cd540f2ef97665b88e1cd877";
  const extendedEvidence = {
    ...evidence,
    commits: [
      {
        sha: productSha,
        short_sha: "a6199ed",
        subject: "feat: add DeepSeek Harness agent integration (#30)",
        source_refs: ["a6199ed", productSha, "#30"],
      },
      {
        sha: automationSha,
        short_sha: "9c57e9c",
        subject: "ci: fix CLI release trigger and permissions",
        source_refs: ["9c57e9c", automationSha],
      },
      {
        sha: mergeSha,
        short_sha: "cd568a3",
        subject: "Merge pull request #31 from MemTensor/docs-sync/memos-cli-release-trigger-fix",
        source_refs: ["cd568a3", mergeSha, "#31"],
      },
    ],
    pull_requests: [{ number: "30" }, { number: "31" }],
    important_commits: [
      {
        sha: productSha,
        short_sha: "a6199ed",
        subject: "feat: add DeepSeek Harness agent integration (#30)",
      },
    ],
    required_source_refs: [
      {
        short_sha: "a6199ed",
        accepted_refs: ["a6199ed", productSha, "#30"],
      },
    ],
  };
  const response = {
    ...validDraft,
    release_items: [
      {
        ...validDraft.release_items[0],
        text_cn:
          "**DeepSeek Harness 集成**：初始化时生成适配的代理指引，便于直接连接 MemOS 记忆能力。",
        text_en:
          "**DeepSeek Harness integration**: Generates compatible agent guidance during initialization so MemOS memory can be connected directly.",
        source_refs: ["a6199ed", "#30"],
      },
      {
        category: "Improved",
        text_cn: "**发布流程**：调整内部发布检查，使自动化运行更加稳定。",
        text_en:
          "**Release workflow**: Adjusted internal release checks for more stable automation.",
        source_refs: ["9c57e9c", "cd568a3"],
      },
    ],
  };
  let requestCount = 0;
  try {
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL =
      "https://example.invalid/draft";
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN = "test-token";
    globalThis.fetch = async () => {
      requestCount += 1;
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify(response),
      };
    };

    const result = await requestDocAgentDraft(extendedEvidence);
    assert.equal(requestCount, 3);
    assert.equal(result.validation_report.ok, true);
    assert.equal(result.validation_attempt_count, 1);
    assert.equal(result.repair_attempt_count, 0);
    assert.equal(result.release_items.length, 1);
    assert.deepEqual(result.release_items[0].source_refs, ["a6199ed", "#30"]);
    assert.equal(result.evidence_curation.removed_item_count, 1);
    assert.equal(result.evidence_curation.removed_source_ref_count, 2);
  } finally {
    globalThis.fetch = previousFetch;
    if (previousUrl === undefined) {
      delete process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL;
    } else {
      process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL = previousUrl;
    }
    if (previousToken === undefined) {
      delete process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN;
    } else {
      process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN = previousToken;
    }
  }
});

test("sends deterministic validation feedback to Doc Agent for repair", async () => {
  const previousFetch = globalThis.fetch;
  const previousUrl = process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL;
  const previousToken = process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN;
  const requests = [];
  const invalidDraft = {
    ok: true,
    needs_review: false,
    release_items: [
      {
        category: "Fixed",
        text_cn: "**登录错误提示**：修复登录失败信息。",
        text_en: "**Authentication errors**: Clarified sign-in failures.",
        source_refs: ["not-real"],
      },
    ],
  };
  const responses = [invalidDraft, invalidDraft, invalidDraft, validDraft];
  try {
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL =
      "https://example.invalid/draft";
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN = "test-token";
    globalThis.fetch = async (_url, options) => {
      requests.push(JSON.parse(options.body));
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify(responses.shift()),
      };
    };
    const result = await requestDocAgentDraft(evidence);
    assert.equal(result.validation_report.ok, true);
    assert.equal(result.validation_attempt_count, 2);
    assert.equal(result.repair_attempt_count, 1);
    assert.equal(requests.length, 4);
    assert.ok(
      requests[3].repair_context.validation_report.issues.some(
        (item) => item.kind === "invalid_source_ref",
      ),
    );
  } finally {
    globalThis.fetch = previousFetch;
    if (previousUrl === undefined) {
      delete process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL;
    } else {
      process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL = previousUrl;
    }
    if (previousToken === undefined) {
      delete process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN;
    } else {
      process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN = previousToken;
    }
  }
});

test("fails closed and reports three exhausted semantic repairs", async () => {
  const previousFetch = globalThis.fetch;
  const previousDraftUrl = process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL;
  const previousFailureUrl = process.env.DOC_AGENT_RELEASE_FAILURE_URL;
  const previousToken = process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN;
  const invalidDraft = {
    ok: true,
    needs_review: false,
    release_items: [
      {
        category: "Fixed",
        text_cn: "**认证**：修复了认证问题。",
        text_en: "**Authentication**: Fixed an authentication issue.",
        source_refs: ["not-real"],
      },
    ],
  };
  let draftRequests = 0;
  let failurePayload;
  try {
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL =
      "https://example.invalid/draft";
    process.env.DOC_AGENT_RELEASE_FAILURE_URL =
      "https://example.invalid/failure";
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN = "test-token";
    globalThis.fetch = async (url, options) => {
      if (url === "https://example.invalid/failure") {
        failurePayload = JSON.parse(options.body);
        return {
          ok: true,
          status: 200,
          text: async () => JSON.stringify({ ok: true }),
        };
      }
      draftRequests += 1;
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify(invalidDraft),
      };
    };
    await assert.rejects(
      requestDocAgentDraft(evidence),
      /failed 3 repair attempts/,
    );
    assert.equal(draftRequests, 6);
    assert.equal(failurePayload.phase, "release-notes-validation");
    assert.equal(failurePayload.attempts.length, 3);
    assert.ok(
      failurePayload.attempts.every(
        (item) => item.error_code === "RELEASE_NOTES_VALIDATION",
      ),
    );
  } finally {
    globalThis.fetch = previousFetch;
    if (previousDraftUrl === undefined) {
      delete process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL;
    } else {
      process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_URL = previousDraftUrl;
    }
    if (previousFailureUrl === undefined) {
      delete process.env.DOC_AGENT_RELEASE_FAILURE_URL;
    } else {
      process.env.DOC_AGENT_RELEASE_FAILURE_URL = previousFailureUrl;
    }
    if (previousToken === undefined) {
      delete process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN;
    } else {
      process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN = previousToken;
    }
  }
});

test("reports only three exhausted attempts and redacts failure details", async () => {
  const previousUrl = process.env.DOC_AGENT_RELEASE_FAILURE_URL;
  const previousToken = process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN;
  let request;
  const sensitiveMessage = `${fakeBearerCredential()} at http://10.1.2.3/internal`;
  try {
    process.env.DOC_AGENT_RELEASE_FAILURE_URL =
      "https://example.invalid/failure";
    process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN = "test-token";
    const result = await reportFailure(
      {
        evidence,
        attempts: [1, 2, 3].map((attempt) => ({
          error_code: "RELEASE_NOTES_VALIDATION",
          message:
            attempt === 3
              ? sensitiveMessage
              : `validation attempt ${attempt}`,
          retryable: false,
        })),
        finalError: sensitiveMessage,
        phase: "release-notes-validation",
      },
      {
        fetchImpl: async (url, options) => {
          request = { url, options, body: JSON.parse(options.body) };
          return {
            ok: true,
            status: 200,
            text: async () => JSON.stringify({ ok: true }),
          };
        },
      },
    );
    assert.equal(result.ok, true);
    assert.equal(request.url, "https://example.invalid/failure");
    assert.equal(request.body.attempts.length, 3);
    assert.equal(request.body.product_id, "memos-cloud-cli");
    assert.equal(request.body.repository, "MemTensor/MemOS-Cloud-CLI");
    assert.equal(request.body.version, "v1.0.7");
    assert.doesNotMatch(JSON.stringify(request.body), /ghp_|10\.1\.2\.3/);
  } finally {
    if (previousUrl === undefined) {
      delete process.env.DOC_AGENT_RELEASE_FAILURE_URL;
    } else {
      process.env.DOC_AGENT_RELEASE_FAILURE_URL = previousUrl;
    }
    if (previousToken === undefined) {
      delete process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN;
    } else {
      process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN = previousToken;
    }
  }
});

test("redacts broad credential and internal address patterns", () => {
  const secretValue = ["abcdef", "1234567890"].join("");
  const privateKeyBlock = [
    `-----BEGIN ${"PRIVATE"} KEY-----`,
    secretValue,
    `-----END ${"PRIVATE"} KEY-----`,
  ].join("\n");
  const value = [
    "private ip 10.1.2.3",
    `api_${"key"}=${secretValue}`,
    `Authorization: Basic ${secretValue}`,
    `${fakeBearerCredential()} at https://doc-agent.example.internal/internal/draft`,
    privateKeyBlock,
  ].join("\n");
  const result = redact(value);
  assert.equal(hasSensitiveContent(value), true);
  assert.doesNotMatch(result, /10\.1\.2\.3/);
  assert.doesNotMatch(result, new RegExp(secretValue));
  assert.doesNotMatch(result, /Authorization: Basic/);
  assert.doesNotMatch(result, /PRIVATE KEY/);
  assert.doesNotMatch(result, /doc-agent\.example\.internal/);
});

test("rejects sensitive GitHub-generated Release notes before artifacts", async () => {
  const previousFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => ({
      ok: true,
      text: async () =>
        JSON.stringify({
          name: "MemOS CLI v2.0.0",
          body: `## What's Changed\n\n* ${fakeBearerCredential()} at http://10.1.2.3/internal\n`,
        }),
    });
    await assert.rejects(
      () =>
        generateGitHubReleaseNotes({
          repo: "MemTensor/MemOS-Cloud-CLI",
          currentTag: "v2.0.0",
          targetSha: "abc1234",
          previousTag: "v0.1.0-beta.14",
          token: "test-token",
        }),
      /GitHub generated release notes contains credential-like or internal content/,
    );
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test("rejects invalid refs, language mixing, raw commits, and missed evidence", () => {
  const result = validateDraft(
    {
      ok: true,
      needs_review: false,
      release_items: [
        {
          category: "Improved",
          text_cn: "fix(auth): 修复登录失败。",
          text_en: "修复 authentication failures.",
          source_refs: ["not-real"],
        },
      ],
    },
    evidence,
  );
  assert.equal(result.ok, false);
  assert.ok(result.issues.some((item) => item.kind === "invalid_text_en"));
  assert.ok(result.issues.some((item) => item.kind === "raw_commit_subject"));
  assert.ok(result.issues.some((item) => item.kind === "invalid_source_ref"));
  assert.ok(result.issues.some((item) => item.kind === "missing_required_ref"));

  const sensitiveRefResult = validateDraft(
    {
      ...validDraft,
      release_items: [
        {
          ...validDraft.release_items[0],
          source_refs: ["https://doc-agent.example.internal/source"],
        },
      ],
    },
    evidence,
  );
  assert.ok(
    sensitiveRefResult.issues.some(
      (item) => item.kind === "sensitive_source_ref",
    ),
  );
});

test("rejects a real source ref when it belongs only to release automation", () => {
  const automationSha = "def5678000000000000000000000000000000000";
  const result = validateDraft(
    {
      ...validDraft,
      release_items: [
        validDraft.release_items[0],
        {
          category: "Improved",
          text_cn:
            "**发布流程**：调整内部发布检查，使自动化运行更加稳定。",
          text_en:
            "**Release workflow**: Adjusted internal release checks for more stable automation.",
          source_refs: ["def5678"],
        },
      ],
    },
    {
      ...evidence,
      commits: [
        ...evidence.commits,
        {
          sha: automationSha,
          short_sha: "def5678",
          subject: "fix(ci): repair release workflow",
          source_refs: ["def5678", automationSha],
        },
      ],
    },
  );
  assert.ok(
    result.issues.some(
      (item) =>
        item.kind === "non_user_facing_source_refs" && item.index === 1,
    ),
  );
});

test("deterministically removes release items backed only by automation evidence", () => {
  const automationSha = "def5678000000000000000000000000000000000";
  const extendedEvidence = {
    ...evidence,
    commits: [
      ...evidence.commits,
      {
        sha: automationSha,
        short_sha: "def5678",
        subject: "fix(ci): repair release workflow",
        source_refs: ["def5678", automationSha, "#99"],
      },
    ],
    pull_requests: [...evidence.pull_requests, { number: "99" }],
  };
  const result = curateDraftByEvidence(
    {
      ...validDraft,
      release_items: [
        validDraft.release_items[0],
        {
          category: "Improved",
          text_cn:
            "**发布流程**：调整内部发布检查，使自动化运行更加稳定。",
          text_en:
            "**Release workflow**: Adjusted internal release checks for more stable automation.",
          source_refs: ["def5678", "#99"],
        },
      ],
    },
    extendedEvidence,
  );

  assert.equal(result.release_items.length, 1);
  assert.deepEqual(result.release_items[0].source_refs, ["abc1234", "#31"]);
  assert.equal(result.evidence_curation.removed_item_count, 1);
  assert.equal(result.evidence_curation.removed_source_ref_count, 2);
  assert.equal(validateDraft(result, extendedEvidence).ok, true);
});

test("strips known automation refs from an otherwise user-facing item", () => {
  const automationSha = "def5678000000000000000000000000000000000";
  const extendedEvidence = {
    ...evidence,
    commits: [
      ...evidence.commits,
      {
        sha: automationSha,
        short_sha: "def5678",
        subject: "fix(ci): repair release workflow",
        source_refs: ["def5678", automationSha],
      },
    ],
  };
  const result = curateDraftByEvidence(
    {
      ...validDraft,
      release_items: [
        {
          ...validDraft.release_items[0],
          source_refs: ["abc1234", "def5678", "#31"],
        },
      ],
    },
    extendedEvidence,
  );

  assert.deepEqual(result.release_items[0].source_refs, ["abc1234", "#31"]);
  assert.equal(result.evidence_curation.removed_item_count, 0);
  assert.equal(result.evidence_curation.removed_source_ref_count, 1);
  assert.equal(validateDraft(result, extendedEvidence).ok, true);
});

test("preserves unknown refs so malformed Doc Agent output still fails closed", () => {
  const result = curateDraftByEvidence(
    {
      ...validDraft,
      release_items: [
        {
          ...validDraft.release_items[0],
          source_refs: ["not-real"],
        },
      ],
    },
    evidence,
  );

  assert.deepEqual(result.release_items[0].source_refs, ["not-real"]);
  assert.equal(result.evidence_curation.removed_item_count, 0);
  assert.ok(
    validateDraft(result, evidence).issues.some(
      (item) => item.kind === "invalid_source_ref",
    ),
  );
});

test("still fails closed when Doc Agent returns only automation items", () => {
  const automationSha = "def5678000000000000000000000000000000000";
  const extendedEvidence = {
    ...evidence,
    commits: [
      ...evidence.commits,
      {
        sha: automationSha,
        short_sha: "def5678",
        subject: "fix(ci): repair release workflow",
        source_refs: ["def5678", automationSha],
      },
    ],
  };
  const result = curateDraftByEvidence(
    {
      ...validDraft,
      release_items: [
        {
          category: "Improved",
          text_cn:
            "**发布流程**：调整内部发布检查，使自动化运行更加稳定。",
          text_en:
            "**Release workflow**: Adjusted internal release checks for more stable automation.",
          source_refs: ["def5678"],
        },
      ],
    },
    extendedEvidence,
  );
  const validation = validateDraft(result, extendedEvidence);

  assert.equal(result.release_items.length, 0);
  assert.equal(validation.ok, false);
  assert.ok(
    validation.issues.some((item) => item.kind === "empty_release_items"),
  );
  assert.ok(
    validation.issues.some((item) => item.kind === "missing_required_ref"),
  );
});

test("rejects all generated items when the release has no user-facing changes", () => {
  const result = validateDraft(validDraft, {
    ...evidence,
    has_user_facing_product_changes: false,
    required_source_refs: [],
  });
  assert.ok(
    result.issues.some(
      (item) => item.kind === "unexpected_release_items_without_user_changes",
    ),
  );
});

test("rejects generic Plugin tab copy without concrete CLI impact", () => {
  const result = validateDraft(
    {
      ok: true,
      needs_review: false,
      release_items: [
        {
          category: "Fixed",
          text_cn: "**认证**：修复了认证问题。",
          text_en: "**Authentication**: Fixed an authentication issue.",
          source_refs: ["abc1234"],
        },
      ],
    },
    evidence,
  );
  assert.ok(result.issues.some((item) => item.kind === "generic_text_cn"));
  assert.ok(result.issues.some((item) => item.kind === "generic_text_en"));
});

test("fault injection exercises every remote-repair quality gate", () => {
  const expectedIssues = new Map([
    ["mixed_language", "invalid_text_en"],
    ["missing_source_refs", "missing_source_refs"],
    ["invalid_source_ref", "invalid_source_ref"],
    ["missing_important_commit", "missing_required_ref"],
    ["thirteen_items", "too_many_release_items"],
    ["too_long", "text_cn_too_long"],
  ]);
  for (const [faultCase, expectedIssue] of expectedIssues) {
    const injected = injectDraftFault(validDraft, evidence, faultCase);
    const validation = validateDraft(injected, evidence);
    assert.equal(validation.ok, false, faultCase);
    assert.ok(
      validation.issues.some((item) => item.kind === expectedIssue),
      `${faultCase} should produce ${expectedIssue}`,
    );
  }
  assert.equal(
    injectDraftFault(validDraft, evidence, "mixed_language", {
      validationRound: 2,
    }),
    validDraft,
  );
});

test("rejects credentials and private URLs in generated website copy", () => {
  const result = validateDraft(
    {
      ok: true,
      needs_review: false,
      release_items: [
        {
          ...validDraft.release_items[0],
          text_cn:
            "**登录错误提示**：请访问 http://10.1.2.3/internal 查看认证失败原因。",
          text_en:
            `**Authentication errors**: Use ${fakeBearerCredential()} to inspect failures.`,
        },
      ],
    },
    evidence,
  );
  assert.ok(result.issues.some((item) => item.kind === "sensitive_content"));
  assert.equal(
    redact("see https://doc-agent.example.internal/internal/draft"),
    "see [REDACTED_INTERNAL_URL]",
  );
});

test("rejects fragmented and overlong Plugin tab content", () => {
  const fragmented = {
    ok: true,
    needs_review: false,
    release_items: Array.from({ length: 13 }, (_, index) => ({
      category: "Improved",
      text_cn: `**CLI 优化 ${index}**：改善命令使用体验。`,
      text_en: `**CLI improvement ${index}**: Improved command usability.`,
      source_refs: ["abc1234"],
    })),
  };
  const fragmentedResult = validateDraft(fragmented, evidence);
  assert.ok(
    fragmentedResult.issues.some(
      (item) => item.kind === "too_many_release_items",
    ),
  );

  const longResult = validateDraft(
    {
      ok: true,
      needs_review: false,
      release_items: [
        {
          ...validDraft.release_items[0],
          text_cn: `**登录错误提示**：${"用于验证官网条目长度限制的中文说明。".repeat(20)}`,
          text_en: `**Authentication errors**: ${"This sentence verifies the maximum length for website changelog entries. ".repeat(10)}`,
        },
      ],
    },
    evidence,
  );
  assert.ok(longResult.issues.some((item) => item.kind === "text_cn_too_long"));
  assert.ok(longResult.issues.some((item) => item.kind === "text_en_too_long"));
});

test("renders only the two Plugin changelog targets and exposes source refs", () => {
  const preview = buildDocsPreview(validDraft, evidence);
  assert.deepEqual(preview.files, [
    "content/cn/plugin-changelog.yml",
    "content/en/plugin-changelog.yml",
  ]);
  assert.equal(preview.evidence_scope, "whole_repository");
  assert.deepEqual(preview.product_paths, ["**"]);
  assert.deepEqual(preview.release_items[0].source_refs, ["abc1234", "#31"]);
  assert.equal(preview.would_create_docs_pr, false);
  assert.equal(
    preview.cn.products.plugin["Bug Fixes"][0].type,
    "MemOS CLI",
  );
  const markdown = docsPreviewMarkdown(preview, validDraft, evidence);
  assert.match(markdown, /refs: abc1234, #31/);
});

test("release workflow preserves two existing build targets and uses a draft-first release", () => {
  const workflow = readFileSync(".github/workflows/release.yml", "utf8");
  const publishScript = readFileSync(PUBLISH_SCRIPT_PATH, "utf8");
  assert.doesNotThrow(() =>
    execFileSync("bash", ["-n", PUBLISH_SCRIPT_PATH], {
      stdio: ["ignore", "pipe", "pipe"],
    }),
  );
  assert.match(workflow, /version:/);
  assert.match(workflow, /target_ref:/);
  assert.match(workflow, /dry_run:/);
  assert.match(workflow, /publish_confirmation:/);
  assert.match(workflow, /create_draft_release:/);
  assert.match(workflow, /CREATE_DRAFT_RELEASE:/);
  assert.match(workflow, /recover_existing_release:/);
  assert.match(workflow, /fault_case:/);
  assert.match(workflow, /mixed_language/);
  assert.match(workflow, /missing_important_commit/);
  assert.match(workflow, /thirteen_items/);
  assert.match(workflow, /default:\s+true/);
  assert.match(workflow, /PUBLISH v<version>/);
  assert.match(workflow, /push:\n\s+branches: \[main\]/);
  assert.match(workflow, /node \.github\/scripts\/resolve-cli-release\.mjs/);
  assert.match(workflow, /PUSH_REF/);
  assert.match(workflow, /PUSH_BEFORE_SHA/);
  assert.match(workflow, /PUSH_AFTER_SHA/);
  assert.doesNotMatch(workflow, /PR_HEAD_REPO|PR_BASE_SHA|PR_MERGE_SHA/);
  assert.match(
    workflow,
    /resolve:\n[\s\S]*?github\.event\.after[\s\S]*?persist-credentials: false[\s\S]*?node \.github\/scripts\/resolve-cli-release\.mjs/,
  );
  assert.match(
    workflow,
    /ref: \$\{\{ github\.event\.repository\.default_branch \}\}/,
  );
  assert.match(
    workflow,
    /ref: \$\{\{ needs\.prepare\.outputs\.target_sha \}\}/,
  );
  assert.match(
    workflow,
    /prepare:\n[\s\S]*?persist-credentials: false\n[\s\S]*?\n  build:/,
  );
  assert.match(
    workflow,
    /build:\n[\s\S]*?persist-credentials: false\n[\s\S]*?\n  release:/,
  );
  assert.match(workflow, /release:\n[\s\S]*?persist-credentials: true/);
  assert.match(
    workflow,
    /release:\n[\s\S]*?actions\/setup-node@v4[\s\S]*?node-version: 22/,
  );
  assert.match(workflow, /DOC_AGENT_RELEASE_FAILURE_URL/);
  assert.match(workflow, /if: \$\{\{ always\(\) \}\}/);
  assert.match(workflow, /permissions:\n\s+contents: read/);
  assert.match(
    workflow,
    /resolve:\n[\s\S]*?permissions:\n\s+contents: read[\s\S]*?\n  prepare:/,
  );
  assert.match(
    workflow,
    /prepare:\n[\s\S]*?permissions:[\s\S]*?contents: write[\s\S]*?\n  build:/,
  );
  assert.match(
    workflow,
    /build:\n[\s\S]*?permissions:\n\s+contents: read[\s\S]*?\n  release:/,
  );
  assert.match(workflow, /release:\n[\s\S]*permissions:\n\s+contents: write/);
  assert.match(publishScript, /recover_existing_release=true/);
  assert.match(workflow, /ubuntu-22\.04/);
  assert.match(workflow, /windows-2022/);
  assert.match(
    workflow,
    /build:\n\s+if: >-[\s\S]*?needs\.resolve\.outputs\.eligible == 'true'[\s\S]*?needs\.resolve\.outputs\.dry_run != 'true'/,
  );
  assert.doesNotMatch(workflow, /build:\n\s+if: \$\{\{ !inputs\.dry_run \}\}/);
  assert.doesNotMatch(workflow, /macos-/);
  assert.doesNotMatch(workflow, /checksum|sha-256|sha256/i);
  assert.match(workflow, /github-release-notes\.md/);
  assert.match(workflow, /release-notes-source\.json/);
  assert.match(workflow, /bash \.github\/scripts\/publish-cli-release\.sh/);
  assert.match(publishScript, /release_flags=\(--draft\)/);
  assert.match(publishScript, /gh release create[\s\S]*--verify-tag/);
  assert.match(publishScript, /git config --local user\.name/);
  assert.match(publishScript, /collect_release_assets/);
  assert.match(publishScript, /release_assets=\(dist\/\*\.tar\.gz\)/);
  assert.match(publishScript, /gh release edit[\s\S]*--draft/);
  assert.match(
    publishScript,
    /Publish the draft manually to emit release\.published/,
  );
  assert.doesNotMatch(publishScript, /gh release create[\s\S]*--latest/);
  assert.match(publishScript, /trusted_main_push/);
  assert.match(publishScript, /merge-base --is-ancestor/);
});

test("publish state machine creates only a Draft Release for a new stable tag", () => {
  const result = runPublishFixture();
  assert.equal(result.failure, undefined);
  assert.match(
    result.callLog,
    new RegExp(`git tag ${result.currentTag} ${result.targetSha}`),
  );
  assert.match(result.callLog, new RegExp(`git push origin refs/tags/${result.currentTag}`));
  assert.match(result.callLog, /gh release create[\s\S]*--draft/);
  assert.doesNotMatch(result.callLog, /--prerelease/);
  assert.match(result.output, /Draft Release created/);
});

test("publish state machine waits for pushed tags and newly created Draft Releases to become visible", () => {
  const result = runPublishFixture({
    tagVisibilityDelay: 2,
    releaseVisibilityDelay: 1,
    assetVisibilityDelay: 2,
  });
  assert.equal(result.failure, undefined);
  assert.equal((result.callLog.match(/git push origin/g) || []).length, 1);
  assert.equal((result.callLog.match(/gh release create/g) || []).length, 1);
  assert.ok((result.callLog.match(/git ls-remote --tags/g) || []).length >= 4);
  assert.ok((result.callLog.match(/gh release view/g) || []).length >= 5);
  assert.match(result.output, /Draft Release created/);
});

test("publish state machine reconciles an ambiguous tag push without pushing twice", () => {
  const reconciled = runPublishFixture({
    tagPushStatus: 1,
    tagPushMaterializes: true,
    tagVisibilityDelay: 1,
  });
  assert.equal(reconciled.failure, undefined);
  assert.equal((reconciled.callLog.match(/git push origin/g) || []).length, 1);
  assert.equal((reconciled.callLog.match(/gh release create/g) || []).length, 1);
  assert.match(reconciled.output, /continuing without pushing twice/);

  const missing = runPublishFixture({
    tagPushStatus: 1,
    tagPushMaterializes: false,
  });
  assert.ok(missing.failure);
  assert.equal((missing.callLog.match(/git push origin/g) || []).length, 1);
  assert.doesNotMatch(missing.callLog, /gh release create/);
  assert.match(missing.output, /Refusing to issue a second push/);
});

test("publish state machine reconciles an ambiguous create response without creating twice", () => {
  const reconciled = runPublishFixture({
    releaseCreateStatus: 1,
    releaseCreateMaterializes: true,
    releaseVisibilityDelay: 1,
  });
  assert.equal(reconciled.failure, undefined);
  assert.equal((reconciled.callLog.match(/gh release create/g) || []).length, 1);

  const missing = runPublishFixture({
    releaseCreateStatus: 1,
    releaseCreateMaterializes: false,
  });
  assert.ok(missing.failure);
  assert.equal((missing.callLog.match(/gh release create/g) || []).length, 1);
  assert.match(missing.output, /no matching Draft became visible/);
});

test("publish state machine resumes an incomplete Draft instead of creating a second Release", () => {
  const result = runPublishFixture({
    releaseCreateStatus: 1,
    releaseCreateMaterializes: true,
    assetVisibilityDelay: 100,
  });
  assert.equal(result.failure, undefined);
  assert.equal((result.callLog.match(/gh release create/g) || []).length, 1);
  assert.equal((result.callLog.match(/gh release upload/g) || []).length, 1);
  assert.match(result.output, /safely resuming the Draft upload/);
});

test("publish state machine rechecks main before release mutation", () => {
  const result = runPublishFixture({
    remoteMainSha: "def5678000000000000000000000000000000000",
  });
  assert.ok(result.failure);
  assert.match(result.output, /main moved to/);
  assert.doesNotMatch(
    result.callLog,
    /git tag |git push |gh release upload|gh release edit|gh release create/,
  );
});

test("publish state machine accepts a trusted main push target still contained in main", () => {
  const result = runPublishFixture({
    remoteMainSha: "def5678000000000000000000000000000000000",
    releaseSourceMode: "trusted_main_push",
  });
  assert.equal(result.failure, undefined);
  assert.match(result.callLog, /git fetch --no-tags origin/);
  assert.match(result.callLog, /git merge-base --is-ancestor/);
  assert.match(result.callLog, /gh release create[\s\S]*--draft/);
});

test("publish state machine requires explicit recovery for a matching orphan tag", () => {
  const targetSha = "abc1234000000000000000000000000000000000";
  const blocked = runPublishFixture({ remoteTagSha: targetSha });
  assert.ok(blocked.failure);
  assert.match(blocked.output, /recover_existing_release=true/);
  assert.doesNotMatch(blocked.callLog, /git tag |git push |gh release create/);

  const recovered = runPublishFixture({
    remoteTagSha: targetSha,
    recover: "true",
  });
  assert.equal(recovered.failure, undefined);
  assert.doesNotMatch(recovered.callLog, /git tag |git push /);
  assert.match(recovered.callLog, /gh release create[\s\S]*--draft/);
});

test("publish state machine verifies npm gitHead before explicit recovery", () => {
  const targetSha = "abc1234000000000000000000000000000000000";
  const missingAuthorization = runPublishFixture({
    npmVersionExists: "true",
    npmGitHead: targetSha,
  });
  assert.ok(missingAuthorization.failure);
  assert.match(missingAuthorization.output, /explicit recover_existing_release=true/);
  assert.doesNotMatch(
    missingAuthorization.callLog,
    /git tag |git push |gh release create/,
  );

  const conflicting = runPublishFixture({
    recover: "true",
    npmVersionExists: "true",
    npmGitHead: "c".repeat(40),
  });
  assert.ok(conflicting.failure);
  assert.match(conflicting.output, /expected immutable release target/);
  assert.doesNotMatch(conflicting.callLog, /git tag |git push |gh release create/);

  const verified = runPublishFixture({
    recover: "true",
    npmVersionExists: "true",
    npmGitHead: targetSha,
  });
  assert.equal(verified.failure, undefined);
  assert.match(verified.output, /Verified existing npm/);
  assert.match(verified.callLog, /gh release create/);
});

test("publish state machine fails closed when npm changes after inspection", () => {
  const targetSha = "abc1234000000000000000000000000000000000";
  const appeared = runPublishFixture({
    npmVersionExists: "false",
    liveNpmVersionExists: "true",
    liveNpmGitHead: targetSha,
  });
  assert.ok(appeared.failure);
  assert.match(appeared.output, /npm state changed after release inspection/);
  assert.doesNotMatch(appeared.callLog, /git tag |git push |gh release create/);

  const changedHead = runPublishFixture({
    recover: "true",
    npmVersionExists: "true",
    npmGitHead: targetSha,
    liveNpmVersionExists: "true",
    liveNpmGitHead: "d".repeat(40),
  });
  assert.ok(changedHead.failure);
  assert.match(changedHead.output, /npm gitHead changed after release inspection/);
  assert.doesNotMatch(changedHead.callLog, /git tag |git push |gh release create/);
});

test("publish state machine waits for a matching existing Release before classifying a tag as orphaned", () => {
  const targetSha = "abc1234000000000000000000000000000000000";
  const result = runPublishFixture({
    remoteTagSha: targetSha,
    releaseState: "draft",
    initialReleaseDelayed: true,
    releaseVisibilityDelay: 2,
  });
  assert.equal(result.failure, undefined);
  assert.ok((result.callLog.match(/gh release view/g) || []).length >= 3);
  assert.match(result.callLog, /gh release upload/);
  assert.doesNotMatch(result.output, /recover_existing_release=true/);
});

test("publish state machine resumes a Draft and leaves a published Release unchanged", () => {
  const targetSha = "abc1234000000000000000000000000000000000";
  const draft = runPublishFixture({
    remoteTagSha: targetSha,
    releaseState: "draft",
  });
  assert.equal(draft.failure, undefined);
  assert.match(draft.callLog, /gh release upload/);
  assert.match(draft.callLog, /gh release edit/);
  assert.doesNotMatch(draft.callLog, /gh release create|git tag |git push /);

  const published = runPublishFixture({
    remoteTagSha: targetSha,
    releaseState: "published",
  });
  assert.equal(published.failure, undefined);
  assert.match(published.output, /Published Release already exists/);
  assert.doesNotMatch(
    published.callLog,
    /gh release upload|gh release edit|gh release create|git tag |git push /,
  );
});

test("publish state machine safely retries idempotent Draft upload and edit operations", () => {
  const targetSha = "abc1234000000000000000000000000000000000";
  const result = runPublishFixture({
    remoteTagSha: targetSha,
    releaseState: "draft",
    uploadFailures: 1,
    editFailures: 1,
  });
  assert.equal(result.failure, undefined);
  assert.equal((result.callLog.match(/gh release upload/g) || []).length, 2);
  assert.equal((result.callLog.match(/gh release edit/g) || []).length, 2);
  assert.doesNotMatch(result.callLog, /gh release create|git tag |git push /);
});

test("publish state machine refuses a conflicting tag and marks prereleases", () => {
  const conflict = runPublishFixture({
    remoteTagSha: "def5678000000000000000000000000000000000",
  });
  assert.ok(conflict.failure);
  assert.match(conflict.output, /already exists at/);
  assert.doesNotMatch(conflict.callLog, /gh release view|gh release create|git push /);

  const prerelease = runPublishFixture({ version: "2.0.0-rc.1" });
  assert.equal(prerelease.failure, undefined);
  assert.match(prerelease.callLog, /gh release create[\s\S]*--draft --prerelease/);
});

test("pre/post-merge checks lint workflows and stay isolated from live release permissions", () => {
  const releaseWorkflow = readFileSync(".github/workflows/release.yml", "utf8");
  const checkWorkflow = readFileSync(
    ".github/workflows/release-changelog-ci.yml",
    "utf8",
  );
  assert.doesNotMatch(releaseWorkflow, /\bworkflow_call\s*:/);
  assert.doesNotMatch(
    checkWorkflow,
    /uses:\s*[.'"]*\/\.github\/workflows\/release\.yml/,
  );
  assert.match(checkWorkflow, /permissions:\n\s+contents: read/);
  assert.match(checkWorkflow, /docker:\/\/rhysd\/actionlint@sha256:[0-9a-f]{64}/);
  assert.match(checkWorkflow, /\^\[0-9a-f\]\{40\}\(\[0-9a-f\]\{24\}\)\?\$/);
  assert.match(checkWorkflow, /persist-credentials:\s+false/);
  assert.doesNotMatch(checkWorkflow, /\bsecrets\./);
  assert.doesNotMatch(checkWorkflow, /\bcontents:\s+write\b/);
});

test("the committed baseline audit records npm gitHead as the authoritative point", () => {
  const runbook = readFileSync(
    "docs/release-changelog-automation.md",
    "utf8",
  );
  assert.match(
    runbook,
    /c18ced54beeb817f6d3f0def1d43eca66da94817/,
  );
  assert.match(runbook, /npm.*gitHead/i);
  assert.match(runbook, /do not.*push.*automatically/i);
});
