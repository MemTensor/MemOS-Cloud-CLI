---
name: memos-shared
description: Use this skill for MemOS CLI initialization, authentication, identity propagation, and output conventions before calling any domain skill.
---

# MemOS Shared Protocol

Use this skill when:
- you need to initialize MemOS CLI before first use;
- you need to confirm auth, base URL, or active profile;
- you need to decide which identity fields to pass;
- you need stable machine-readable output conventions before calling another MemOS skill.

Always apply:
- initialize the CLI before domain commands if the environment may be fresh;
- prefer stable identity fields such as `--user-id` and `--conversation-id` when available;
- use per-command `--format` and `--detail` flags deliberately based on whether the consumer is a human, an agent, or a program;
- keep API keys out of logs, prompts, and stored memories.

Use these commands:
- `memos init`
- `memos init --api-key <API_KEY> --base-url https://memos.memtensor.cn/api/openmem/v1`
- `memos config show`
- `memos config get platform.base_url`
- `memos --help`

Identity rules:
- pass `--user-id` when the framework provides a stable user identity;
- pass `--conversation-id` when the framework provides a stable session identity;
- pass `--agent-id` for multi-agent isolation, `--app-id` for app-level isolation, and `--run-id` for per-run tracing when needed;
- append `--api-key` and `--base-url` only when you must override local config.

Source attribution:
- MemOS CLI attaches `X-Source: cli`;
- MemOS CLI may attach `X-Framework` when auto-detected;
- if framework detection fails, set `MEMOS_FRAMEWORK` explicitly.

Example:

```bash
export MEMOS_FRAMEWORK=openclaw
```

Output conventions:
- append `--format table` at the end of a command for terminal browsing and quick inspection;
- append `--format markdown` at the end of a command for copying into issues, PRs, or docs;
- append `--format agent` at the end of a command when the caller needs a JSON envelope plus a model-facing context block;
- append `--format json` at the end of a command for stable programmatic parsing;
- append `--detail simple` or `--detail detail` at the end of a command to control verbosity;
- expect machine-readable outputs to expose fields such as `status`, `command`, `duration_ms`, `scope`, `count`, and `data`.

Common failures:
- `Authentication failed` usually means the API key is invalid or expired;
- `API error` usually means a route, argument, or server response issue;
- missing required arguments should exit non-zero immediately.

Then continue with:

- [`../memos-config/SKILL.md`](../memos-config/SKILL.md)
- [`../memos-memory/SKILL.md`](../memos-memory/SKILL.md)
- [`../memos-kb/SKILL.md`](../memos-kb/SKILL.md)
- [`../memos-memory-agent/SKILL.md`](../memos-memory-agent/SKILL.md)
