---
name: memos-memory
description: Use MemOS to extract, retrieve, persist, inspect, and delete long-term memory for user, project, and task context.
---

# MemOS Memory Protocol

Use this skill when:
- the task may depend on prior user, project, or conversation context;
- the user provides a stable new fact, preference, or background detail;
- you want to preview extracted memory candidates before storing them;
- you need to inspect, list, or delete an existing memory record.

Never store:
- secrets, API keys, tokens, or passwords;
- unverified guesses or speculative conclusions as user facts;
- short-lived task state that will not matter in future sessions;
- redundant paraphrases when one concise factual memory is enough.

Use these commands:
- `memos add "<fact>" --user-id <USER_ID> --format json`
- `memos extract "<message>" --user-id <USER_ID> --format json`
- `memos search "<query>" --user-id <USER_ID> --format agent --detail simple`
- `memos chat "<message>" --user-id <USER_ID> --format agent`
- `memos get <USER_ID> --format json --detail detail`
- `memos delete <MEMORY_ID> --format json`

Choose commands by intent:
- use [`./references/memos-add.md`](./references/memos-add.md) when the user gives a durable fact or preference worth saving;
- use [`./references/memos-extract.md`](./references/memos-extract.md) when the user wants a preview of memory candidates without storing;
- use [`./references/memos-search.md`](./references/memos-search.md) before answering when historical context may matter;
- use [`./references/memos-chat.md`](./references/memos-chat.md) when interacting with MemOS chat capability directly;
- use [`./references/memos-get.md`](./references/memos-get.md) for retrieval by `user_id`;
- use [`./references/memos-delete.md`](./references/memos-delete.md) only when you already have a concrete `memory_id`.

Working rules:
- do not mechanically copy entire messages into search queries; compress them into entities, preferences, and intent;
- append `--format json` at the end of the command whenever a later step needs exact `memory_id` or structured records;
- append `--format agent` at the end of the command when the result will be injected back into model context;
- keep `--format` at the end of every command line, and keep `--detail` at the end only for `search` and `get`;
- initialize MemOS CLI with `memos init` before using memory commands in a fresh environment;
- prefer stable identity fields such as `--user-id` when available;
- read result counts from `count` and structured payloads from `data`;
- if you already have `memory_id`, do not search first just to guess.

Examples:

```bash
memos add "User likes Python"
memos search "Python"
```

```bash
memos search "user preferences about restaurants" --user-id <USER_ID> --format agent --detail simple
```

```bash
memos extract "User likes coffee and prefers dark mode" --user-id <USER_ID> --format json
```

```bash
memos add "User is allergic to peanuts" --user-id <USER_ID> --format json
```

```bash
memos get <USER_ID> --format json --detail detail
memos delete <MEMORY_ID> --format json
```
