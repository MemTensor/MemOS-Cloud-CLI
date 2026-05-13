# `memos chat`

Use this command when:
- you want MemOS to answer using retrieved memory context;
- the task needs a memory-informed response rather than raw retrieval only;
- you want a conversational query against MemOS itself.

Never do:
- use `chat` when you only need deterministic retrieval results and IDs;
- omit identity fields when the answer should stay scoped to one user or conversation;
- treat generated answers as equivalent to raw memory records.

Command:

```bash
memos chat "<query>"
```

Common flags:

- `--user-id`
- `--format agent|json`

Example:

```bash
memos chat "What do you know about my travel preferences?" --user-id user_123 --format agent
```

Working rules:
- `chat` is for memory-informed answers, not plain search;
- pass `--user-id` whenever possible to avoid scope drift.
