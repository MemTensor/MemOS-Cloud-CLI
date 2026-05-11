---
name: memos-memory
description: Use MemOS to extract, retrieve, persist, inspect, and delete long-term memory for user, project, and task context.
---

# MemOS Memory Protocol

Read first:
- [`../memos-shared/SKILL.md`](../memos-shared/SKILL.md)

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
- `memos add -m "<fact>" --user-id <USER_ID> --conversation-id <CONV_ID> --format json`
- `memos extract -m "<message>" --user-id <USER_ID> --conversation-id <CONV_ID> --format json --detail detail`
- `memos search -q "<query>" --user-id <USER_ID> --conversation-id <CONV_ID> --format agent --detail simple`
- `memos list --user-id <USER_ID> --conversation-id <CONV_ID> --format table --detail simple`
- `memos chat -q "<message>" --user-id <USER_ID> --conversation-id <CONV_ID> --format agent --detail detail`
- `memos get <MEMORY_ID> --format json --detail detail`
- `memos delete <MEMORY_ID> --format json`

Choose commands by intent:
- use [`./references/memos-add.md`](./references/memos-add.md) when the user gives a durable fact or preference worth saving;
- use [`./references/memos-extract.md`](./references/memos-extract.md) when the user wants a preview of memory candidates without storing;
- use [`./references/memos-search.md`](./references/memos-search.md) before answering when historical context may matter;
- use [`./references/memos-list.md`](./references/memos-list.md) for browsing, not targeted retrieval;
- use [`./references/memos-chat.md`](./references/memos-chat.md) when interacting with MemOS chat capability directly;
- use [`./references/memos-get.md`](./references/memos-get.md) and [`./references/memos-delete.md`](./references/memos-delete.md) only when you already have a concrete `memory_id`.

Working rules:
- do not mechanically copy entire messages into search queries; compress them into entities, preferences, and intent;
- append `--format json` at the end of the command whenever a later step needs exact `memory_id` or structured records;
- append `--format agent` at the end of the command when the result will be injected back into model context;
- keep `--format` and `--detail` after the command arguments and business options, at the end of the command line;
- read result counts from `count` and structured payloads from `data`;
- if you already have a `memory_id`, do not search first just to guess.

Examples:

```bash
memos add -m "User likes Python"
memos search -q "Python"
```

```bash
memos search -q "user preferences about restaurants" --user-id <USER_ID> --conversation-id <CONV_ID> --format agent --detail simple
```

```bash
memos extract -m "User likes coffee and prefers dark mode" --user-id <USER_ID> --conversation-id <CONV_ID> --format json --detail detail
```

```bash
memos add -m "User is allergic to peanuts" --user-id <USER_ID> --conversation-id <CONV_ID> --format json
```

```bash
memos get <MEMORY_ID> --format json --detail detail
memos delete <MEMORY_ID> --format json
```
