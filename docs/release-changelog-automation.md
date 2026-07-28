# MemOS Cloud CLI release-to-docs automation

This repository uses a standalone-release variant of the MemOS local-plugin
release flow:

> No next CLI version has been selected by this automation. As of the
> 2026-07-28 audit, `main` and npm are still `1.0.6`, and the formal repository
> has no tags or GitHub Releases. Merging this automation creates neither a
> version nor a tag. Wait for the CLI owner to choose `<next-version>`, land
> its actual changes, and update all three version sources before running a
> real dry run.

1. A release operator runs **MemOS CLI — Release** with `version`,
   `target_ref`, `dry_run`, and the draft/recovery safety inputs.
2. A dry run compares the previous SemVer tag with the target commit, requests
   three bilingual Plugin changelog candidates from Doc Agent, validates the
   selected candidate, and uploads a review artifact.
3. A real run requires the exact confirmation `PUBLISH v<version>`, preserves
   the existing Linux and Windows builds, creates the version tag, and creates
   a Draft GitHub Release whose body is GitHub-generated `What's Changed`.
4. A Draft Release is mandatory. Direct publication is rejected so a release
   owner must review the title, body, tag range, and assets first. Publishing
   that draft emits
   `release.published`.
5. Doc Agent maps `MemTensor/MemOS-Cloud-CLI` to `memos-cloud-cli`, compares the
   complete repository between the previous and current tags, and creates a
   MemOS-Docs Draft PR only after its evidence and bilingual quality gates pass.
6. The docs pipeline may proceed through pre and gray. Production remains a
   manual decision after the CLI owner reviews gray.

The GitHub Release body and the website copy intentionally have different
roles. GitHub's body is the public engineering-oriented `What's Changed`.
Doc Agent creates the shorter Chinese and English Plugin tab copy from the
same Git tag range after `release.published`.

## Verified v1.0.6 baseline

The authoritative baseline for `v1.0.6` is:

```text
c18ced54beeb817f6d3f0def1d43eca66da94817
```

Evidence:

- `npm view @memtensor/memos-cloud-cli@1.0.6 ...` reports
  `gitHead=c18ced54beeb817f6d3f0def1d43eca66da94817`.
- npm reports the `1.0.6` publication time as
  `2026-07-22T09:22:21.408Z`.
- The commit was created at `2026-07-22T16:45:57+08:00`, before the npm
  publication.
- At that commit, `package.json`, `pyproject.toml`, and
  `src/memos_cli/__init__.py` all declare version `1.0.6`.
- The commit is reachable from `origin/main`.
- The repository had no remote tags and no GitHub Releases when this baseline
  was audited.

The version-bump commit `b8b722f` is too early: a subsequent build cleanup is
included in the npm package's recorded `gitHead`. The merge commit `73619ff`
is too late and does not match npm's recorded source commit.

Backfill only the verified tag; do not create a fake historical GitHub Release.
Use this approval flow:

1. Put the evidence above in the automation PR or a dedicated maintainer issue.
2. Ask a maintainer with write access to explicitly comment:
   `APPROVE BACKFILL v1.0.6 c18ced54beeb817f6d3f0def1d43eca66da94817`.
3. The maintainer runs the commands below from a clean checkout. If the remote
   tag already exists or points anywhere else, stop and do not force-push.

```bash
git clone git@github.com:MemTensor/MemOS-Cloud-CLI.git
cd MemOS-Cloud-CLI
git fetch origin main
git ls-remote --tags origin refs/tags/v1.0.6
git rev-parse --verify c18ced54beeb817f6d3f0def1d43eca66da94817^{commit}
git show --no-patch --format='%H%n%s%n%aI' c18ced54beeb817f6d3f0def1d43eca66da94817
git tag v1.0.6 c18ced54beeb817f6d3f0def1d43eca66da94817
git push origin refs/tags/v1.0.6
git ls-remote --tags origin refs/tags/v1.0.6
```

Do not push this tag automatically. A CLI repository maintainer must review the
evidence above and explicitly approve the one-time remote tag backfill. The
release workflow fails closed while the previous SemVer tag is missing, so it
cannot accidentally describe the entire repository history as the next
release.

This baseline is a Git release reference. It is unrelated to binary SHA-256
manifests; this changelog integration does not add checksum generation.

## Required repository secrets

The release inspection and exhausted-failure path require these encrypted
repository secrets:

```text
DOC_AGENT_RELEASE_NOTES_DRAFT_URL
DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN
DOC_AGENT_RELEASE_FAILURE_URL
```

The values must be GitHub Actions encrypted secrets. Never put the URL or token
in source, workflow defaults, artifacts, or logs. The failure endpoint is
best-effort: it receives only three exhausted, redacted attempt summaries and
can never hide the original release error.

Endpoint URLs may use HTTP or HTTPS. The current 106 Doc Agent deployment uses
HTTP, so keep both URLs only in GitHub Actions encrypted secrets and never in
source, workflow defaults, artifacts, or logs. The failure endpoint must use
the same origin as the draft endpoint because both calls share the draft Bearer
token.

The release continues to use GitHub's short-lived `github.token`. This
changelog-only change does not add npm, OSS, or deployment credentials.
GitHub's generate-notes API requires `contents: write`, so that permission is
limited to the `prepare` and `release` jobs; the workflow default and build job
remain read-only.

## Required Doc Agent mapping

The deployed `release_changelog_targets.yaml` must identify the standalone CLI
repository and collect its entire tag range:

```yaml
sources:
  - id: memos-cloud-cli
    trigger: github_release
    source_repo: MemTensor/MemOS-Cloud-CLI
    tag_patterns:
      - 'v*'
    # The current 106 collector enters evidence collection through
    # product_paths. '**' means the complete standalone CLI repository.
    product_paths:
      - '**'
    format: memos_docs_plugin_changelog
    renderer_options:
      product_title:
        zh: MemOS CLI
        en: MemOS CLI
    docs:
      repo: MemTensor/MemOS-Docs
      branch: v2
      files:
        zh: content/cn/plugin-changelog.yml
        en: content/en/plugin-changelog.yml
```

There is no CLI subdirectory filter. The `**` compatibility value means
"whole repository"; it does not distinguish MemOS from a local-plugin path.
The mapping must never point to `content/{cn,en}/changelog.yml`, which is
reserved for Highlight updates.

The GitHub webhook must subscribe to the Release event. A read-only audit on
2026-07-28 confirmed that the formal repository has an active JSON webhook
subscribed to `release`; its creation `ping` was accepted with HTTP 200 and
webhook signature verification is configured on Doc Agent. No real
`release.published` delivery exists yet because this repository still has no
GitHub Releases. The Release-event subscription is present; the current 106
deployment accepts HTTP webhook transport with HMAC signature verification.
The first real Release must still be held until the deployed mapping/version
preview below passes.

The same hook currently also subscribes to `push`. That is not required for
this release-to-docs chain; limiting it to `release` is the least-noise option.
It is not a blocker because Doc Agent routes `push` to a separate, filtered
post-merge checker rather than the release pipeline.

Doc Agent only treats a
non-draft, non-prerelease `release.published` event as the formal docs-sync
entry point. Drafts and prereleases must not create production docs PRs.

The CLI repository can keep this change in one PR, but the deployed Doc Agent
configuration is an external prerequisite. Before the first production
Release, run a Doc Agent preview/replay with a CLI tag range and require all of
the following:

```text
handled=true
source_id=memos-cloud-cli
previous_tag and current_tag are the expected SemVer tags
evidence_scope covers the complete repository
requested_candidate_count=3
missing_required_count=0
would_create_docs_pr=false during preview
only content/{cn,en}/plugin-changelog.yml would change
```

If the deployed service does not return three-candidate selection metadata for
the post-release extraction, deploy the already-reviewed Doc Agent
multi-candidate implementation before enabling the production webhook. Do not
assume that a successful pre-release CLI artifact proves the post-release
service version is current.

## Dry-run procedure

Before the first real release, after the CLI owner has selected the actual next
version:

1. Ensure the verified `v1.0.6` tag is present remotely.
2. Prepare the intended release commit and update all three version sources:
   `package.json`, `pyproject.toml`, and `src/memos_cli/__init__.py`.
3. Run **MemOS CLI — Release** and replace `<next-version>` with the exact
   owner-approved version. In the workflow branch selector, choose the
   protected default branch `main`; use `target_ref` below to inspect another
   branch or commit:

```text
version: <next-version>
target_ref: the branch or commit being inspected
dry_run: true
create_draft_release: true
recover_existing_release: false
fault_case: none
publish_confirmation: empty
```

The `memos-cloud-cli-release-inspection` artifact contains:

- `README.md`: operator-facing decision summary, tag status, quality result,
  and zero-side-effect statement.
- `github-release-notes.md`: preview of the public `What's Changed` body.
- `release-notes.md`: compatibility alias of the same public body preview.
- `evidence.json`: redacted whole-repository commits, changed files, PR
  references, diff statistics, and bounded patch excerpts.
- `release-notes-draft.json`: accepted bilingual Plugin changelog items with
  their internal `source_refs`, candidate selection, and validation result.
- `docs-preview.md` and `docs-preview.json`: the bilingual Plugin tab preview
  with internal `source_refs`.
- `quality-report.json`: candidate selection, coverage, validation, and repair
  attempts.
- `release-contract.json`: trigger, target files, evidence scope, and proof that
  the workflow's dry-run mutation flags are disabled. It also records the
  mandatory Draft-first/manual-publish policy.

The evidence, preview, report, and contract all use
`product_paths: ["**"]`. For this standalone repository, that value means the
complete CLI tag range and keeps the workflow artifact aligned with the
deployed Doc Agent mapping.

A dry run does not build release archives or create a tag, GitHub Release,
Docs PR, or deployment.

For remote acceptance, also verify that `refs/tags/v<version>` is still absent
and that the GitHub Releases API returns no matching Release. The artifact
records the contract; these read-only GitHub checks prove external state.

After the normal dry run succeeds, the release owner can run a dry-run-only
fault matrix. Each case corrupts only the first candidate round; validation
must reject it, send the exact issue report to the repair request, and accept a
valid repaired response:

```text
mixed_language
missing_source_refs
invalid_source_ref
missing_important_commit
thirteen_items
too_long
```

Every fault run must keep `dry_run=true`. A live run with any `fault_case`
other than `none` fails before build, tag, or Release mutation.

If the preparation script starts and then fails, the workflow still uploads
the same artifact schema, including `README.md`, the public notes files,
`release-notes-draft.json`, evidence, previews, report, and contract.
`quality-report.json` has `ok=false`, the phase, and a redacted error;
`docs-preview.json` has `docs_action=blocked_by_quality_gate`. This makes a
failed remote run diagnosable without exposing endpoint or token values.

Pull requests and pushes to `main` also run
**MemOS CLI Release — Pre/Post-Merge Checks**. It exports
`memos-cloud-cli-release-contract-check`, a synthetic offline
`v99.99.98...v99.99.99` artifact. This deliberately impossible production
version proves the artifact schema, quality gates,
source references, and zero-side-effect contract without requiring production
Doc Agent secrets. It is a mechanism check, not a preview of the next real CLI
release. The same check runs actionlint before Node tests so invalid workflow
syntax, expressions, action inputs, or job definitions fail on the PR rather
than at release time. It is read-only, does not call the live release workflow,
and has no access to Doc Agent secrets.

## Real release procedure

After the dry-run artifact is approved and the release commit is on `main`,
run the owner-approved version:

```text
version: <next-version>
target_ref: main
dry_run: false
create_draft_release: true
recover_existing_release: false
fault_case: none
publish_confirmation: PUBLISH v<next-version>
```

The workflow:

- refuses live releases from a ref other than `main`;
- refuses live dispatches whose workflow ref or target commit is not the
  current protected default branch;
- refuses `create_draft_release=false`; every live run must stop at a Draft
  Release for manual review;
- refuses a mismatched version file;
- refuses a missing previous SemVer tag;
- refuses to move an existing tag to another commit;
- rechecks remote `refs/heads/main` immediately before creating or updating a
  Draft Release, so a main branch advance during build requires a new dry run;
- builds only the two targets already supported by this repository;
- creates or safely resumes a Draft Release;
- leaves an already-published Release unchanged.

Evidence curation also ignores changes that are clearly release machinery
rather than CLI behavior, including `fix(ci):` / `fix(build):` scopes and
commits whose changed files are limited to workflow, test, or documentation
paths. These commits remain visible in raw evidence but do not force a Plugin
tab entry.

If a prior run pushed the correct tag but failed before creating the GitHub
Release, the normal rerun stops. After confirming that the tag points to the
intended commit and that no Release exists, rerun once with
`recover_existing_release=true`. This explicit recovery prevents an old tag
from being backfilled as a new Release by accident.

Review the Draft Release and its assets, then publish it manually. That manual
publication is what sends `release.published` to Doc Agent.

## Post-release quality and recovery

Doc Agent must fail closed before opening a Docs PR when any of these conditions
occur:

- the previous tag cannot be determined;
- one or more of the three independent candidate requests fails to return a
  candidate for local scoring;
- a referenced commit or PR does not exist in the tag-range evidence;
- an important feature, fix, performance, or refactor commit is uncovered;
- Chinese or English text is missing or mixed into the wrong language;
- content contains an internal URL or credential-like value;
- copy merely says that a feature/problem/performance was added/fixed/improved
  without explaining concrete CLI impact;
- there are more than 12 entries;
- a Chinese item exceeds 180 characters or an English item exceeds 220;
- three validation/repair attempts are exhausted.

Repeated delivery of the same release must be idempotent. If the CLI version
already exists in `plugin-changelog.yml`, Doc Agent should report an
already-present result instead of appending a duplicate.

If gray review finds incorrect copy, fix the MemOS-Docs Draft PR or create a
corrective Docs PR, run pre and gray again, and keep production blocked until
the CLI owner approves it.

## Explicit non-goals

This integration does not:

- add macOS or a four-platform build matrix;
- add SHA-256 or checksum manifests;
- change npm publishing;
- change OSS uploads or the npm postinstall download path;
- put Doc Agent's generated website copy into the GitHub Release body;
- allow GitHub Release publication to bypass the exact confirmation phrase;
- automate production deployment.
