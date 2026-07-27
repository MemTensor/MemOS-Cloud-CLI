#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";

export const PRODUCT_ID = "memos-cloud-cli";
export const PRODUCT_TITLE = { zh: "MemOS CLI", en: "MemOS CLI" };

const REPOSITORY = "MemTensor/MemOS-Cloud-CLI";
const RELEASE_NOTES_MARKER = "doc-agent-release-notes-json";
const RELEASE_CATEGORY_ORDER = ["Added", "Improved", "Fixed"];
const RELEASE_TO_DOC_CATEGORY = {
  Added: "New Features",
  Improved: "Improvements",
  Fixed: "Bug Fixes",
};
const RELEASE_ASSET_TARGETS = ["darwin-arm64", "darwin-x64", "linux-x64", "windows-x64"];
const MAX_DRAFT_REPAIR_ATTEMPTS = 3;
const MAX_RELEASE_ITEMS = 12;
const MAX_TEXT_CN_CHARS = 180;
const MAX_TEXT_EN_CHARS = 220;
const CJK_RE = /[\u3400-\u9fff\uf900-\ufaff]/;

export const RELEASE_NOTE_LIMITS = {
  max_items: MAX_RELEASE_ITEMS,
  max_text_cn_chars: MAX_TEXT_CN_CHARS,
  max_text_en_chars: MAX_TEXT_EN_CHARS,
  max_repair_attempts: MAX_DRAFT_REPAIR_ATTEMPTS,
};

export const RELEASE_NOTE_QUALITY_REQUEST = {
  schema: "memos.plugin.release_notes.quality_request.v1",
  candidate_count: 3,
  selection_policy: [
    "Generate multiple candidate CLI release-note drafts when supported.",
    "Score candidates against evidence coverage, source_ref validity, bilingual language separation, installer/binary accuracy, and docs-preview readability.",
    "Return only the best candidate in release_items/release_notes_markdown; include candidate scoring metadata only in debug fields when available.",
  ],
  repair_policy: {
    max_repair_attempts: MAX_DRAFT_REPAIR_ATTEMPTS,
    use_validation_report: true,
    fail_closed_after_exhaustion: true,
  },
};

function fail(message) {
  throw new Error(String(message));
}

function warn(message) {
  console.error(`::warning::${message}`);
}

function git(args, options = {}) {
  return execFileSync("git", args, {
    cwd: process.cwd(),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  }).trim();
}

function gitText(args) {
  try {
    return git(args);
  } catch {
    return "";
  }
}

function requiredEnv(name) {
  const value = String(process.env[name] || "").trim();
  if (!value) fail(`${name} is required.`);
  return value;
}

export function cleanVersion(raw) {
  const value = String(raw || "").trim().replace(/^v/, "");
  if (
    !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/.test(
      value,
    )
  ) {
    fail(`Invalid release version: ${raw || "(empty)"}`);
  }
  return value;
}

export function parseSemver(raw) {
  const match = String(raw || "")
    .replace(/^v/, "")
    .match(
      /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/,
    );
  if (!match) return null;
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
    prerelease: match[4] || "",
  };
}

function comparePrereleaseIdentifiers(left, right) {
  const leftNumeric = /^(0|[1-9]\d*)$/.test(left);
  const rightNumeric = /^(0|[1-9]\d*)$/.test(right);
  if (leftNumeric && rightNumeric) return Number(left) - Number(right);
  if (leftNumeric) return -1;
  if (rightNumeric) return 1;
  return left < right ? -1 : left > right ? 1 : 0;
}

function comparePrerelease(left, right) {
  if (left === right) return 0;
  if (!left) return 1;
  if (!right) return -1;

  const leftParts = left.split(".");
  const rightParts = right.split(".");
  const length = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = leftParts[index];
    const rightPart = rightParts[index];
    if (leftPart === undefined) return -1;
    if (rightPart === undefined) return 1;
    const order = comparePrereleaseIdentifiers(leftPart, rightPart);
    if (order !== 0) return order;
  }
  return 0;
}

export function compareSemver(a, b) {
  const left = parseSemver(a);
  const right = parseSemver(b);
  if (!left || !right) return String(a).localeCompare(String(b));
  for (const key of ["major", "minor", "patch"]) {
    if (left[key] !== right[key]) return left[key] - right[key];
  }
  return comparePrerelease(left.prerelease, right.prerelease);
}

export function resolvePreviousRef(targetVersion, currentTag, explicitRef = "") {
  const ref = String(explicitRef || "").trim();
  if (ref) {
    git(["rev-parse", "--verify", `${ref}^{commit}`]);
    return ref;
  }

  const localTagsBeforeFetch = listLocalCliTags();
  try {
    git(["fetch", "--tags", "--force", "origin"], { stdio: ["ignore", "ignore", "ignore"] });
  } catch {
    if (localTagsBeforeFetch.length === 0) {
      warn("Failed to fetch tags; using local tags.");
    }
  }

  const tag = listLocalCliTags()
    .filter((item) => item !== currentTag && parseSemver(item) && compareSemver(item, targetVersion) < 0)
    .sort((a, b) => compareSemver(b, a))[0];
  if (!tag) {
    fail("No real previous CLI tag exists. Backfill a baseline tag first, or provide RELEASE_PREVIOUS_REF only from a migration-only caller.");
  }
  return tag;
}

function listLocalCliTags() {
  return git(["tag", "--list", "v*"])
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function readJsonFile(file) {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return {};
  }
}

function gitShowJson(ref, file) {
  try {
    return JSON.parse(git(["show", `${ref}:${file}`]));
  } catch {
    return {};
  }
}

function tagInfo(ref, label = ref) {
  const text = git(["show", "--no-patch", "--format=%H%n%ci%n%s", `${ref}^{commit}`]);
  const [sha = "", date = "", subject = ""] = text.split("\n");
  return { tag: label, ref, sha, date, subject };
}

function commits(range) {
  return git(["log", "--format=%H%x09%h%x09%s", "--no-merges", range])
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      const [sha = "", short_sha = "", subject = ""] = line.split("\t");
      return { sha, short_sha, subject };
    });
}

function files(range) {
  return git(["diff", "--name-status", range])
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      const parts = line.split("\t");
      return { status: parts[0], path: parts.at(-1), ...(parts.length === 3 ? { old_path: parts[1] } : {}) };
    });
}

function versionFromToml(text) {
  return String(text || "").match(/version\s*=\s*"([^"]+)"/)?.[1] || "";
}

function versionFromInit(text) {
  return String(text || "").match(/__version__\s*=\s*"([^"]+)"/)?.[1] || "";
}

function versionFileChanges(previousRef) {
  const previousPackage = gitShowJson(previousRef, "package.json");
  const currentPackage = readJsonFile("package.json");
  const previousPyproject = versionFromToml(gitText(["show", `${previousRef}:pyproject.toml`]));
  const currentPyproject = versionFromToml(readFileSync("pyproject.toml", "utf8"));
  const previousInit = versionFromInit(gitText(["show", `${previousRef}:src/memos_cli/__init__.py`]));
  const currentInit = versionFromInit(readFileSync("src/memos_cli/__init__.py", "utf8"));
  return [
    { file: "package.json", before: previousPackage.version || "", after: currentPackage.version || "" },
    { file: "pyproject.toml", before: previousPyproject, after: currentPyproject },
    { file: "src/memos_cli/__init__.py", before: previousInit, after: currentInit },
  ].filter((item) => item.before !== item.after);
}

function releaseAssetContractForEvidence() {
  const contract = readJsonFile("release-assets.json");
  return {
    schema: contract.schema || 1,
    targets: Array.isArray(contract.targets) ? contract.targets : RELEASE_ASSET_TARGETS,
    public_base_url_configured: Boolean(contract.public_base_url),
  };
}

function refsForGuidance(commit) {
  const refs = [];
  if (commit.short_sha) refs.push(commit.short_sha);
  for (const match of String(commit.subject || "").matchAll(/#(\d+)/g)) {
    const ref = `#${match[1]}`;
    if (!refs.includes(ref)) refs.push(ref);
  }
  return refs;
}

function categoryHintForSubject(subject) {
  const value = String(subject || "");
  const lower = value.toLowerCase();
  if (lower.startsWith("release:") || /^chore(\([^)]+\))?:\s*(release|version|bump)\b/i.test(value) || /^test(\([^)]+\))?:/i.test(value)) {
    return null;
  }
  if (/^(feat|feature|add)(\([^)]+\))?:|^add\s+/i.test(value)) {
    return { category: "Added", reason: "new user-facing CLI capability or command behavior" };
  }
  if (/^(perf|performance|refactor|improve|enhance)(\([^)]+\))?:/i.test(value) || /build|pack|publish|postinstall|pyinstaller|binary|installer|oss|sync-version/i.test(value)) {
    return { category: "Improved", reason: "CLI packaging, installer, compatibility, or reliability improvement" };
  }
  if (/^(fix|hotfix|bugfix)(\([^)]+\))?:|^fix\s+#\d+/i.test(value)) {
    return { category: "Fixed", reason: "specific CLI bug fix" };
  }
  return null;
}

function releaseNoteGuidanceForCommits(commitList) {
  return {
    category_policy: {
      Added: "Use for newly exposed CLI commands, options, workflows, or installation capabilities.",
      Improved: "Use for packaging, binary distribution, compatibility, docs, postinstall, OSS, or release reliability improvements.",
      Fixed: "Use for concrete broken CLI behavior, installer failures, API path regressions, encoding issues, or binary launch failures.",
    },
    source_ref_category_hints: commitList
      .map((commit) => {
        const hint = categoryHintForSubject(commit.subject);
        const source_refs = refsForGuidance(commit);
        return hint && source_refs.length ? { ...hint, source_refs, subject: commit.subject } : null;
      })
      .filter(Boolean),
  };
}

export function collectEvidence({ targetVersion, currentTag, previousRef }) {
  const range = `${previousRef}..HEAD`;
  const commitList = commits(range);
  const changed = files(range);
  const repo = process.env.GITHUB_REPOSITORY || REPOSITORY;
  const numbers = new Set(commitList.flatMap((item) => [...item.subject.matchAll(/#(\d+)/g)].map((match) => match[1])));
  const previousPackage = gitShowJson(previousRef, "package.json");
  const currentPackage = readJsonFile("package.json");
  const releaseAssetContract = releaseAssetContractForEvidence();

  return {
    product_id: PRODUCT_ID,
    product_title: PRODUCT_TITLE,
    release_note_quality_request: RELEASE_NOTE_QUALITY_REQUEST,
    release_note_guidance: releaseNoteGuidanceForCommits(commitList),
    repo,
    previous_tag: previousRef,
    current_tag: currentTag,
    current_ref: "HEAD",
    diff_range: range,
    target_version: `v${cleanVersion(targetVersion)}`,
    git_ref: git(["rev-parse", "--short=12", "HEAD"]),
    previous: tagInfo(previousRef),
    current: tagInfo("HEAD", currentTag),
    commits: commitList,
    pull_requests: [...numbers].map((number) => ({ number, url: `https://github.com/${repo}/pull/${number}` })),
    changed_files: changed,
    diff_stat: git(["diff", "--stat", range]),
    important_diff: {
      "cli/**": git([
        "diff",
        "--unified=2",
        range,
        "--",
        "src",
        "scripts",
        "package.json",
        "pyproject.toml",
        "README.md",
        "README-zh.md",
        "npm/README.md",
        "skills/memos-memory",
      ]).slice(0, 24000),
    },
    package_changes: ["name", "version"]
      .filter((key) => previousPackage[key] !== currentPackage[key])
      .map((key) => ({ field: key, before: previousPackage[key], after: currentPackage[key] })),
    version_file_changes: versionFileChanges(previousRef),
    release_asset_contract: releaseAssetContract,
    postinstall_contract: {
      asset_pattern: "memos-<version>-<target>.tar.gz",
      supported_targets: releaseAssetContract.targets,
      skip_download_env: "MEMOS_INSTALL_SKIP_DOWNLOAD",
      override_url_env: "MEMOS_BINARY_URL",
    },
    test_changes: changed.filter((item) => item.path.startsWith("tests/") || item.path.endsWith(".test.js") || item.path.endsWith(".test.mjs")),
    docs_changes: changed.filter((item) => /^README|^npm\/README|^docs\/|^skills\/memos-memory\//i.test(item.path)),
  };
}

export function evidenceForInspection(evidence) {
  const {
    important_diff: _importantDiff,
    release_note_guidance: guidance = {},
    release_note_quality_request: _releaseNoteQualityRequest,
    ...publicEvidence
  } = evidence || {};
  return {
    ...publicEvidence,
    release_note_guidance: {
      source_ref_category_hints: Array.isArray(guidance.source_ref_category_hints) ? guidance.source_ref_category_hints : [],
    },
    redactions: {
      important_diff: "omitted from public workflow artifacts; sent only to the configured draft service",
      prompt_guidance: "omitted from public workflow artifacts",
      release_note_quality_request: "omitted from public workflow artifacts; sent only to the configured draft service",
    },
  };
}

export function draftForInspection(draft) {
  return {
    ok: Boolean(draft?.ok),
    needs_review: Boolean(draft?.needs_review),
    confidence: draft?.confidence || "",
    release_items: Array.isArray(draft?.release_items) ? draft.release_items : [],
    coverage: draft?.coverage || {},
    warnings: Array.isArray(draft?.warnings) ? draft.warnings : [],
    docs_categories: draft?.docs_categories || { cn: {}, en: {} },
    language_issues: Array.isArray(draft?.language_issues) ? draft.language_issues : [],
    readability_issues: Array.isArray(draft?.readability_issues) ? draft.readability_issues : [],
    postprocess: draft?.postprocess || {},
    validation_report: draft?.validation_report || {},
    validation_attempt_count: Number(draft?.validation_attempt_count || 0),
    repair_attempt_count: Number(draft?.repair_attempt_count || 0),
    repair_attempts: Array.isArray(draft?.repair_attempts) ? draft.repair_attempts : [],
    redactions: {
      server_debug_fields: "omitted from public workflow artifacts",
      model_and_prompt_details: "omitted from public workflow artifacts",
    },
  };
}

function appendOutput(name, value) {
  if (!process.env.GITHUB_OUTPUT) return;
  writeFileSync(process.env.GITHUB_OUTPUT, `${name}<<__DOC_AGENT_EOF__\n${value}\n__DOC_AGENT_EOF__\n`, {
    flag: "a",
  });
}

export function ensureSourceHint(notes) {
  const hint = `<!-- doc-agent: source-id=${PRODUCT_ID} -->`;
  return notes.includes("doc-agent: source-id=") ? `${notes.trim()}\n` : `${notes.trim()}\n\n${hint}\n`;
}

function normalizeReleaseItem(raw) {
  const category = RELEASE_CATEGORY_ORDER.includes(String(raw?.category || "").trim()) ? String(raw.category).trim() : "";
  const text_cn = String(raw?.text_cn || "").trim().replace(/^-+\s*/, "");
  const text_en = String(raw?.text_en || "").trim().replace(/^-+\s*/, "");
  const source_refs = Array.isArray(raw?.source_refs)
    ? raw.source_refs.map(normalizeSourceRef).filter(Boolean)
    : [];
  return category && text_cn && text_en && source_refs.length ? { category, text_cn, text_en, source_refs } : null;
}

function normalizeSourceRef(value) {
  const text = String(value || "").trim().replace(/^[`[(\s]+|[`)\],.;\s]+$/g, "");
  if (/^#\d+$/.test(text)) return text;
  if (/^[a-fA-F0-9]{7,40}$/.test(text)) return text.toLowerCase();
  if (/^\d{2,}$/.test(text)) return `#${text}`;
  return "";
}

function sourceRefsForCommit(commit) {
  const refs = [];
  if (commit.short_sha) refs.push(String(commit.short_sha).toLowerCase());
  if (commit.sha) refs.push(String(commit.sha).toLowerCase());
  for (const match of String(commit.subject || "").matchAll(/#(\d+)/g)) refs.push(`#${match[1]}`);
  return [...new Set(refs.map(normalizeSourceRef).filter(Boolean))];
}

function evidenceSourceIndex(evidence) {
  const validRefs = new Set();
  const required = [];
  for (const commit of Array.isArray(evidence?.commits) ? evidence.commits : []) {
    const refs = sourceRefsForCommit(commit);
    refs.forEach((ref) => validRefs.add(ref));
    if (categoryHintForSubject(commit.subject)) {
      required.push({
        subject: commit.subject,
        refs,
        preferred_ref: refs[0] || "",
      });
    }
  }
  for (const pr of Array.isArray(evidence?.pull_requests) ? evidence.pull_requests : []) {
    const ref = normalizeSourceRef(`#${pr.number}`);
    if (ref) validRefs.add(ref);
  }
  return { validRefs, required };
}

function languageIssuesFromReleaseItems(items) {
  const issues = [];
  items.forEach((item, index) => {
    if (!CJK_RE.test(item.text_cn)) {
      issues.push({ index, field: "text_cn", issue: "Chinese output must contain Chinese/CJK text." });
    }
    if (CJK_RE.test(item.text_en)) {
      issues.push({ index, field: "text_en", issue: "English output must not contain Chinese/CJK text." });
    }
  });
  return issues;
}

function readabilityIssuesFromReleaseItems(items) {
  const issues = [];
  if (items.length > MAX_RELEASE_ITEMS) {
    issues.push({
      field: "release_items",
      item_count: items.length,
      max_item_count: MAX_RELEASE_ITEMS,
      issue: "Plugin changelog output must be grouped into concise product-facing bullets.",
    });
  }
  items.forEach((item, index) => {
    if (item.text_cn && item.text_cn.length > MAX_TEXT_CN_CHARS) {
      issues.push({
        index,
        field: "text_cn",
        current_length: item.text_cn.length,
        max_length: MAX_TEXT_CN_CHARS,
        issue: "Chinese release-note text is too long for the Plugin tab.",
      });
    }
    if (item.text_en && item.text_en.length > MAX_TEXT_EN_CHARS) {
      issues.push({
        index,
        field: "text_en",
        current_length: item.text_en.length,
        max_length: MAX_TEXT_EN_CHARS,
        issue: "English release-note text is too long for the Plugin tab.",
      });
    }
  });
  return issues;
}

function categoriesFromReleaseItems(items) {
  const releaseCategories = {};
  const docsCategories = { cn: {}, en: {} };
  for (const item of items) {
    if (!releaseCategories[item.category]) releaseCategories[item.category] = [];
    releaseCategories[item.category].push(item);

    const docsCategory = RELEASE_TO_DOC_CATEGORY[item.category];
    if (!docsCategory) continue;
    if (!docsCategories.cn[docsCategory]) docsCategories.cn[docsCategory] = [];
    if (!docsCategories.en[docsCategory]) docsCategories.en[docsCategory] = [];
    docsCategories.cn[docsCategory].push(item.text_cn);
    docsCategories.en[docsCategory].push(item.text_en);
  }
  return { releaseCategories, docsCategories };
}

function markdownFromReleaseItems(items, coverage) {
  const lines = ["## Changelog", ""];
  for (const category of RELEASE_CATEGORY_ORDER) {
    const categoryItems = items.filter((item) => item.category === category);
    if (!categoryItems.length) continue;
    lines.push(`### ${category}`, "");
    for (const item of categoryItems) lines.push(`- ${item.text_en}`);
    lines.push("");
  }
  const payload = { items, coverage };
  lines.push(`<!-- ${RELEASE_NOTES_MARKER}`, JSON.stringify(payload), "-->");
  return `${lines.join("\n").trim()}\n`;
}

function coverageFromReleaseItems(evidence, draft, items) {
  const index = evidenceSourceIndex(evidence);
  const usedRefs = new Set(items.flatMap((item) => item.source_refs));
  const invalid_source_refs = [...usedRefs].filter((ref) => !index.validRefs.has(ref));
  const missing_required_refs = index.required
    .filter((required) => !required.refs.some((ref) => usedRefs.has(ref)))
    .map((required) => ({
      source_ref: required.preferred_ref,
      subject: required.subject,
    }));
  return {
    ...(draft?.coverage || {}),
    required_count: index.required.length,
    covered_required_count: Math.max(0, index.required.length - missing_required_refs.length),
    missing_required_count: missing_required_refs.length,
    missing_required_refs,
    invalid_source_refs,
    needs_review: Boolean(draft?.coverage?.needs_review) || missing_required_refs.length > 0 || invalid_source_refs.length > 0,
  };
}

export function postprocessDraftFromEvidence(evidence, draft) {
  const rawItems = Array.isArray(draft?.release_items) ? draft.release_items : Array.isArray(draft?.items) ? draft.items : [];
  const items = rawItems.map(normalizeReleaseItem).filter(Boolean);
  const languageIssues = languageIssuesFromReleaseItems(items);
  const readabilityIssues = readabilityIssuesFromReleaseItems(items);
  const coverage = coverageFromReleaseItems(evidence, draft, items);
  if (languageIssues.length > 0 || readabilityIssues.length > 0 || items.length === 0) coverage.needs_review = true;
  const { releaseCategories, docsCategories } = categoriesFromReleaseItems(items);
  const validationIssues = [
    ...(items.length ? [] : [{ issue: "release_items is empty after normalization" }]),
    ...languageIssues,
    ...readabilityIssues,
    ...(coverage.invalid_source_refs || []).map((ref) => ({ field: "source_refs", source_ref: ref, issue: "source_ref is not present in git evidence" })),
    ...(coverage.missing_required_refs || []).map((item) => ({ field: "coverage", source_ref: item.source_ref, subject: item.subject, issue: "important commit is not covered by any release note item" })),
  ];
  const warnings = Array.isArray(draft?.warnings) ? [...draft.warnings] : [];
  if (validationIssues.length > 0) warnings.push("release notes failed local validation and require repair before publishing");
  if (readabilityIssues.length > 0) warnings.push("release notes readability validation failed; the Plugin tab draft must be repaired before publishing");
  return {
    ...draft,
    ok: items.length > 0 && !coverage.needs_review,
    needs_review: Boolean(coverage.needs_review),
    release_items: items,
    release_categories: releaseCategories,
    docs_categories: docsCategories,
    coverage,
    warnings,
    language_issues: languageIssues,
    readability_issues: readabilityIssues,
    validation_report: {
      ok: validationIssues.length === 0,
      issue_count: validationIssues.length,
      language_issue_count: languageIssues.length,
      readability_issue_count: readabilityIssues.length,
      issues: validationIssues,
    },
    release_notes_markdown: markdownFromReleaseItems(items, coverage),
  };
}

function previewDateFromPublishedAt(value) {
  const text = String(value || "").trim();
  if (!text) return "<GitHub Release published_at>";
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return "<GitHub Release published_at>";
  return date.toISOString().slice(0, 10);
}

export function docsPreviewFromDraft(draft, { targetVersion, publishedAt = "" } = {}) {
  const version = `v${cleanVersion(targetVersion || draft?.target_version || "0.0.0")}`;
  const date = previewDateFromPublishedAt(publishedAt);
  const docsCategories = draft?.docs_categories || { cn: {}, en: {} };
  const buildEntry = (locale) => ({
    name: version,
    date,
    products: {
      plugin: Object.fromEntries(
        Object.entries(docsCategories[locale] || {}).map(([category, items]) => [
          category,
          [{ type: PRODUCT_TITLE[locale === "cn" ? "zh" : "en"], changedInfo: items }],
        ]),
      ),
    },
  });
  return {
    schema: "memos.plugin.docs_preview.v1",
    product_id: PRODUCT_ID,
    repo: REPOSITORY,
    version,
    date,
    date_source: publishedAt ? "provided published_at" : "GitHub Release published_at at publish time",
    docs_files: {
      cn: "content/cn/plugin-changelog.yml",
      en: "content/en/plugin-changelog.yml",
    },
    entries: {
      cn: buildEntry("cn"),
      en: buildEntry("en"),
    },
  };
}

export function markdownFromDocsPreview(preview) {
  const lines = [
    "# MemOS-Docs Plugin Changelog Preview",
    "",
    `- product_id: ${preview.product_id}`,
    `- version: ${preview.version}`,
    `- date: ${preview.date}`,
    `- zh file: ${preview.docs_files.cn}`,
    `- en file: ${preview.docs_files.en}`,
  ];
  for (const [locale, title] of [["cn", "中文预览"], ["en", "English Preview"]]) {
    lines.push("", `## ${title}`);
    const plugin = preview.entries[locale]?.products?.plugin || {};
    const categories = Object.keys(plugin);
    if (categories.length === 0) {
      lines.push("", "- No plugin changelog items would be rendered.");
      continue;
    }
    for (const category of categories) {
      lines.push("", `### ${category}`);
      for (const group of plugin[category] || []) {
        lines.push("", `- type: ${group.type}`);
        for (const item of group.changedInfo || []) lines.push(`  - ${item}`);
      }
    }
  }
  return `${lines.join("\n").trim()}\n`;
}

function releaseNotesPayloadFromDraft(draft) {
  const rawItems = Array.isArray(draft?.release_items) ? draft.release_items : Array.isArray(draft?.items) ? draft.items : [];
  const items = rawItems.map(normalizeReleaseItem).filter(Boolean);
  return { items, coverage: draft?.coverage || { needs_review: Boolean(draft?.needs_review) } };
}

function ensureMachineReadablePayload(notes, draft) {
  if (notes.includes(RELEASE_NOTES_MARKER)) return notes;
  const payload = releaseNotesPayloadFromDraft(draft);
  if (!payload.items.length) {
    fail("Doc Agent draft did not include release_items/source_refs for the hidden docs payload.");
  }
  return `${notes.trim()}\n\n<!-- ${RELEASE_NOTES_MARKER}\n${JSON.stringify(payload)}\n-->\n`;
}

export function validateManualNotes(notes) {
  const text = String(notes || "").trim();
  if (!/^## Changelog\s*$/m.test(text)) fail("Manual release notes require a ## Changelog heading.");
  const payload = manualPayloadFromNotes(text);
  if (!Array.isArray(payload?.items) || payload.items.length === 0 || payload?.coverage?.needs_review !== false) {
    fail("Manual release-note evidence must have non-empty items and passed coverage.");
  }
  const items = payload.items.map(normalizeReleaseItem).filter(Boolean);
  const languageIssues = languageIssuesFromReleaseItems(items);
  const readabilityIssues = readabilityIssuesFromReleaseItems(items);
  if (items.length !== payload.items.length) {
    fail("Manual release-note evidence has invalid categories, text, or source_refs.");
  }
  if (languageIssues.length > 0) {
    fail("Manual release-note evidence must keep Chinese text in text_cn and English text in text_en.");
  }
  if (readabilityIssues.length > 0) {
    fail("Manual release-note items must stay concise enough for the Plugin tab preview.");
  }
  return text;
}

function manualPayloadFromNotes(notes) {
  const match = String(notes || "").match(new RegExp(`<!--\\s*${RELEASE_NOTES_MARKER}\\s*\\n([\\s\\S]*?)\\n-->`));
  if (!match) fail("Manual release notes require the doc-agent-release-notes-json evidence block.");
  try {
    return JSON.parse(match[1]);
  } catch {
    fail("Manual release-note evidence JSON is invalid.");
  }
}

export function manualDraftFromEvidence(evidence, notes) {
  const validNotes = ensureSourceHint(validateManualNotes(notes));
  const payload = manualPayloadFromNotes(validNotes);
  const draft = postprocessDraftFromEvidence(evidence, {
    ok: true,
    needs_review: false,
    confidence: "manual",
    release_items: payload.items,
    coverage: payload.coverage,
    warnings: [],
  });
  return {
    ...draft,
    confidence: "manual",
    validation_attempt_count: 1,
    repair_attempt_count: 0,
    repair_attempts: [
      {
        stage: "manual",
        attempt: 1,
        ok: draft.ok,
        needs_review: draft.needs_review,
        validation_report: draft.validation_report,
      },
    ],
    postprocess: {
      applied: true,
      source: "manual_release_notes",
      final_item_count: draft.release_items.length,
    },
    release_notes_markdown: validNotes,
  };
}

export function qualityReportFromDraft(
  draft,
  { targetVersion = "", previousRef = "", currentTag = "", currentRef = "HEAD", draftUsed = true } = {},
) {
  const validation = draft?.validation_report || {};
  const coverage = draft?.coverage || {};
  const issues = Array.isArray(validation.issues) ? validation.issues : [];
  const languageIssues = Array.isArray(draft?.language_issues) ? draft.language_issues : [];
  const readabilityIssues = Array.isArray(draft?.readability_issues) ? draft.readability_issues : [];
  const invalidRefs = Array.isArray(coverage.invalid_source_refs) ? coverage.invalid_source_refs : [];
  const missingRequired = Array.isArray(coverage.missing_required_refs) ? coverage.missing_required_refs : [];
  return {
    schema: "memos.plugin.release_notes.quality_report.v1",
    product_id: PRODUCT_ID,
    repo: REPOSITORY,
    target_version: targetVersion ? `v${cleanVersion(targetVersion)}` : "",
    previous_ref: previousRef,
    current_tag: currentTag,
    current_ref: currentRef,
    draft_used: Boolean(draftUsed),
    ok: Boolean(draft?.ok) && !draft?.needs_review && validation.ok !== false,
    needs_review: Boolean(draft?.needs_review) || validation.ok === false,
    limits: RELEASE_NOTE_LIMITS,
    item_count: Array.isArray(draft?.release_items) ? draft.release_items.length : 0,
    issue_count: Number(validation.issue_count ?? issues.length),
    language_issue_count: Number(validation.language_issue_count ?? languageIssues.length),
    readability_issue_count: Number(validation.readability_issue_count ?? readabilityIssues.length),
    invalid_source_ref_count: invalidRefs.length,
    missing_required_count: Number(coverage.missing_required_count ?? missingRequired.length),
    coverage,
    issues,
    validation_attempt_count: Number(draft?.validation_attempt_count || 0),
    repair_attempt_count: Number(draft?.repair_attempt_count || 0),
    attempts: Array.isArray(draft?.repair_attempts) ? draft.repair_attempts : [],
  };
}

function cleanError(value) {
  return String(value || "")
    .replace(/Bearer\s+\S+/gi, "Bearer ***")
    .replace(/sk-[\w-]+/g, "sk-***")
    .replace(/https?:\/\/[^\s"'<>]+/gi, "https://***")
    .replace(/\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b/g, "***")
    .replace(/\s+/g, " ")
    .slice(0, 600);
}

function retryable(status) {
  return [408, 425, 429].includes(status) || status >= 500;
}

async function reportFailure(evidence, attempts, finalError, fetchImpl, phase = "release-notes") {
  if (attempts.length < 3 || !process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN) return;
  const failureUrl = String(process.env.DOC_AGENT_RELEASE_FAILURE_URL || "").trim();
  if (!failureUrl) {
    warn("DOC_AGENT_RELEASE_FAILURE_URL is not configured; skipping exhausted-retry report.");
    return;
  }
  const response = await fetchImpl(failureUrl, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${process.env.DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN}`,
    },
    body: JSON.stringify({
      product_id: PRODUCT_ID,
      repository: evidence.repo,
      version: evidence.target_version,
      phase,
      run_id: process.env.GITHUB_RUN_ID || `${evidence.current_tag}-cli`,
      run_url: process.env.GITHUB_RUN_ID ? `https://github.com/${evidence.repo}/actions/runs/${process.env.GITHUB_RUN_ID}` : "",
      attempts: attempts.slice(0, 3).map((item, index) => ({
        attempt: index + 1,
        error_code: item.error_code || "DRAFT_FAILED",
        message: cleanError(item.message || item.error),
        retryable: Boolean(item.retryable),
      })),
      final_error: cleanError(finalError),
    }),
  });
  if (!response.ok) throw new Error(`Failure-report endpoint returned HTTP ${response.status}`);
}

export async function reportExternalFailureFromEnv({ fetchImpl = fetch } = {}) {
  const phase = String(process.env.RELEASE_FAILURE_PHASE || "").trim();
  const attemptDir = String(process.env.RELEASE_FAILURE_ATTEMPT_DIR || "").trim();
  if (!phase || !attemptDir) fail("RELEASE_FAILURE_PHASE and RELEASE_FAILURE_ATTEMPT_DIR are required.");
  const attempts = [1, 2, 3].map((attempt) => {
    let message = "attempt log is unavailable";
    try {
      message = readFileSync(join(attemptDir, `${attempt}.log`), "utf8");
    } catch {
      // The failure report should not replace the original publish failure.
    }
    return { error_code: phase.toUpperCase().replace(/[^A-Z0-9]+/g, "_"), message: cleanError(message), retryable: true };
  });
  const targetVersion = cleanVersion(process.env.RELEASE_VERSION);
  return reportFailure(
    {
      repo: process.env.GITHUB_REPOSITORY || REPOSITORY,
      target_version: `v${targetVersion}`,
      current_tag: process.env.RELEASE_TAG || `v${targetVersion}`,
    },
    attempts,
    attempts[2].message,
    fetchImpl,
    phase,
  );
}

export async function requestDraft(evidence, { fetchImpl = fetch, sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)) } = {}) {
  const token = requiredEnv("DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN");
  const draftUrl = requiredEnv("DOC_AGENT_RELEASE_NOTES_DRAFT_URL");
  const attempts = [];
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await fetchImpl(draftUrl, {
        method: "POST",
        headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
        body: JSON.stringify({
          ...evidence,
          workflow_retry_context: { attempt, previous_errors: attempts.map((item) => item.message) },
        }),
      });
      const text = await response.text();
      let payload;
      try {
        payload = text ? JSON.parse(text) : {};
      } catch {
        throw Object.assign(new Error(`non-JSON response: HTTP ${response.status}`), {
          retryable: retryable(response.status),
          code: `HTTP_${response.status}`,
        });
      }
      if (!response.ok) {
        throw Object.assign(new Error(`HTTP ${response.status} ${text.slice(0, 400)}`), {
          retryable: retryable(response.status),
          code: `HTTP_${response.status}`,
        });
      }
      if (!payload.ok || payload.needs_review || payload.coverage?.needs_review !== false || (!String(payload.release_notes_markdown || "").trim() && !hasStructuredDraftItems(payload))) {
        const message = `Doc Agent draft requires review: ${JSON.stringify(payload.coverage || {})} ${(payload.warnings || []).join("; ")}`;
        if (hasStructuredDraftItems(payload)) {
          warn(`${message} Continuing with local validation and repair because the draft service returned structured release_items.`);
          return payload;
        }
        if (payload.attempts?.length >= 3) await reportFailure(evidence, payload.attempts, message, fetchImpl);
        fail(message);
      }
      return payload;
    } catch (error) {
      const item = {
        error_code: error?.code || "DRAFT_REQUEST",
        message: cleanError(error?.message || error),
        retryable: Boolean(error?.retryable),
      };
      attempts.push(item);
      if (!item.retryable || attempt === 3) {
        await reportFailure(evidence, attempts, item.message, fetchImpl);
        fail(`Doc Agent draft failed on attempt ${attempt}: ${item.message}`);
      }
      warn(`Draft attempt ${attempt} failed; retrying: ${item.message}`);
      await sleep(250 * 2 ** (attempt - 1));
    }
  }
}

function hasStructuredDraftItems(payload) {
  return Array.isArray(payload?.release_items) && payload.release_items.map(normalizeReleaseItem).some(Boolean);
}

export async function requestValidatedDraft(
  evidence,
  { fetchImpl = fetch, sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)) } = {},
) {
  let draft = postprocessDraftFromEvidence(evidence, await requestDraft(evidence, { fetchImpl, sleep }));
  const repairAttempts = [];
  for (let attempt = 1; draft.needs_review && attempt <= MAX_DRAFT_REPAIR_ATTEMPTS; attempt += 1) {
    warn(
      `CLI release notes validation failed after ${attempt === 1 ? "initial draft validation" : `repair validation attempt ${attempt - 1}`}; requesting draft repair ${attempt}/${MAX_DRAFT_REPAIR_ATTEMPTS}: ${draft.validation_report?.issues?.map((item) => item.field || item.issue).join(", ")}`,
    );
    const repairEvidence = {
      ...evidence,
      release_note_repair_context: {
        attempt,
        max_attempts: MAX_DRAFT_REPAIR_ATTEMPTS,
        validation_report: draft.validation_report,
        previous_release_items: draft.release_items,
        previous_warnings: draft.warnings,
      },
    };
    const repaired = await requestDraft(repairEvidence, { fetchImpl, sleep });
    draft = postprocessDraftFromEvidence(evidence, repaired);
    repairAttempts.push({
      attempt,
      ok: draft.ok,
      needs_review: draft.needs_review,
      validation_report: draft.validation_report,
    });
  }
  return {
    ...draft,
    validation_attempt_count: 1 + repairAttempts.length,
    repair_attempt_count: repairAttempts.length,
    repair_attempts: repairAttempts,
  };
}

async function reportValidationFailureIfExhausted(evidence, draft, fetchImpl = fetch) {
  if (Number(draft?.repair_attempt_count || 0) < MAX_DRAFT_REPAIR_ATTEMPTS) return;
  const repairAttempts = Array.isArray(draft?.repair_attempts) ? draft.repair_attempts : [];
  const attempts = repairAttempts.slice(-MAX_DRAFT_REPAIR_ATTEMPTS).map((item) => ({
    error_code: "RELEASE_NOTES_VALIDATION",
    message: JSON.stringify(item.validation_report || item),
    retryable: true,
  }));
  try {
    await reportFailure(
      evidence,
      attempts,
      JSON.stringify(draft?.validation_report || draft?.coverage || {}),
      fetchImpl,
      "release-notes-validation",
    );
  } catch (error) {
    warn(`Failed to report exhausted release-note validation: ${cleanError(error?.message || error)}`);
  }
}

export async function main() {
  const targetVersion = cleanVersion(process.env.RELEASE_VERSION);
  const currentTag = process.env.RELEASE_TAG || `v${targetVersion}`;
  const notesPath = process.env.RELEASE_NOTES_FILE || join(tmpdir(), `memos-cloud-cli-${targetVersion}-release-notes.md`);
  const evidencePath = process.env.RELEASE_EVIDENCE_FILE || join(tmpdir(), `memos-cloud-cli-${targetVersion}-evidence.json`);
  const draftPath = process.env.RELEASE_DRAFT_FILE || join(tmpdir(), `memos-cloud-cli-${targetVersion}-release-notes-draft.json`);
  const docsPreviewPath = process.env.RELEASE_DOCS_PREVIEW_FILE || join(tmpdir(), `memos-cloud-cli-${targetVersion}-docs-preview.json`);
  const docsPreviewMarkdownPath = process.env.RELEASE_DOCS_PREVIEW_MARKDOWN_FILE || join(tmpdir(), `memos-cloud-cli-${targetVersion}-docs-preview.md`);
  const qualityReportPath = process.env.RELEASE_QUALITY_REPORT_FILE || join(tmpdir(), `memos-cloud-cli-${targetVersion}-quality-report.json`);
  mkdirSync(dirname(notesPath), { recursive: true });
  mkdirSync(dirname(evidencePath), { recursive: true });
  mkdirSync(dirname(draftPath), { recursive: true });
  mkdirSync(dirname(docsPreviewPath), { recursive: true });
  mkdirSync(dirname(docsPreviewMarkdownPath), { recursive: true });
  mkdirSync(dirname(qualityReportPath), { recursive: true });

  const previousRef = resolvePreviousRef(targetVersion, currentTag, process.env.RELEASE_PREVIOUS_REF || "");
  const evidence = collectEvidence({ targetVersion, currentTag, previousRef });
  writeFileSync(evidencePath, JSON.stringify(evidenceForInspection(evidence), null, 2), "utf8");
  const manual = String(process.env.MANUAL_RELEASE_NOTES || "").trim();
  const draftUsed = !manual;
  let draft;
  if (manual) {
    try {
      draft = manualDraftFromEvidence(evidence, manual);
    } catch (error) {
      const issue = { field: "manual_release_notes", issue: cleanError(error?.message || error) };
      draft = {
        ok: false,
        needs_review: true,
        confidence: "manual",
        release_items: [],
        docs_categories: { cn: {}, en: {} },
        coverage: { needs_review: true, missing_required_count: 0, invalid_source_refs: [] },
        warnings: [issue.issue],
        language_issues: [],
        readability_issues: [],
        validation_report: { ok: false, issue_count: 1, language_issue_count: 0, readability_issue_count: 0, issues: [issue] },
        validation_attempt_count: 1,
        repair_attempt_count: 0,
        repair_attempts: [{ stage: "manual", attempt: 1, ok: false, needs_review: true, validation_report: { ok: false, issues: [issue] } }],
        release_notes_markdown: manual,
      };
    }
  } else {
    try {
      draft = await requestValidatedDraft(evidence);
    } catch (error) {
      const issue = { field: "draft_service", issue: cleanError(error?.message || error) };
      draft = {
        ok: false,
        needs_review: true,
        confidence: "failed",
        release_items: [],
        docs_categories: { cn: {}, en: {} },
        coverage: { needs_review: true, missing_required_count: 0, invalid_source_refs: [] },
        warnings: [issue.issue],
        language_issues: [],
        readability_issues: [],
        validation_report: { ok: false, issue_count: 1, language_issue_count: 0, readability_issue_count: 0, issues: [issue] },
        validation_attempt_count: 0,
        repair_attempt_count: 0,
        repair_attempts: [],
        release_notes_markdown: "",
      };
    }
  }

  const docsPreview = docsPreviewFromDraft(draft, { targetVersion });
  const qualityReport = qualityReportFromDraft(draft, {
    targetVersion,
    previousRef,
    currentTag,
    currentRef: "HEAD",
    draftUsed,
  });
  writeFileSync(draftPath, JSON.stringify(draftForInspection(draft), null, 2), "utf8");
  writeFileSync(docsPreviewPath, JSON.stringify(docsPreview, null, 2), "utf8");
  writeFileSync(docsPreviewMarkdownPath, markdownFromDocsPreview(docsPreview), "utf8");
  writeFileSync(qualityReportPath, JSON.stringify(qualityReport, null, 2), "utf8");
  if (String(draft.release_notes_markdown || "").trim()) {
    const notes = draftUsed
      ? ensureSourceHint(ensureMachineReadablePayload(draft.release_notes_markdown, draft))
      : ensureSourceHint(draft.release_notes_markdown);
    writeFileSync(notesPath, notes, "utf8");
  }

  for (const [key, value] of Object.entries({
    release_notes_file: notesPath,
    evidence_file: evidencePath,
    draft_file: draftPath,
    docs_preview_file: docsPreviewPath,
    docs_preview_markdown_file: docsPreviewMarkdownPath,
    quality_report_file: qualityReportPath,
    draft_used: String(draftUsed),
    previous_tag: previousRef,
    current_tag: currentTag,
    current_ref: "HEAD",
    draft_confidence: String(draft.confidence || ""),
    missing_required_count: String(draft.coverage?.missing_required_count ?? ""),
    validation_attempt_count: String(draft.validation_attempt_count ?? ""),
    repair_attempt_count: String(draft.repair_attempt_count ?? ""),
  })) {
    appendOutput(key, value);
  }

  if (!draft.ok || draft.needs_review) {
    if (draftUsed) await reportValidationFailureIfExhausted(evidence, draft);
    fail(`Postprocessed CLI release notes require review: ${JSON.stringify(draft.validation_report || draft.coverage || {})}`);
  }
}

const isDirect = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isDirect) {
  const run = process.env.RELEASE_FAILURE_PHASE ? reportExternalFailureFromEnv : main;
  run().catch((error) => {
    console.error(`::error::${cleanError(error?.message || error)}`);
    process.exitCode = 1;
  });
}
