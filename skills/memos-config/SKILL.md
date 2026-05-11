---
name: memos-config
description: Use this skill to initialize MemOS CLI, inspect configuration, and update connection settings safely.
---

# MemOS Config Protocol

Read first:
- [`../memos-shared/SKILL.md`](../memos-shared/SKILL.md)

Use this skill when:
- MemOS CLI is being set up for the first time;
- auth or base URL settings need verification;
- default configuration values need inspection or update.

Never do:
- print raw API keys into logs or chat replies;
- change config values blindly without first checking current state when debugging;
- assume local config is correct in a fresh environment.

Use these commands:
- `memos init`
- `memos init --api-key <API_KEY> --base-url https://memos.memtensor.cn/api/openmem/v1`
- `memos config show`
- `memos config get <key>`
- `memos config set <key> <value>`

Working rules:
- run `memos init` before the first domain command in a new environment;
- inspect config with `memos config show` before making corrective edits;
- use `memos config get` for targeted checks when only one field matters.

Example:

```bash
memos init --api-key <API_KEY> --base-url https://memos.memtensor.cn/api/openmem/v1
memos config show
memos config get platform.base_url
```
