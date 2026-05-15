# `memos extract`

Use this command when:
- you want to preview memory candidates without storing them;
- the user asks what MemOS would extract from a message;
- you need to inspect candidate memory types before deciding what to save.

Never do:
- treat extracted candidates as already persisted;
- feed long noisy multi-turn transcripts without first compressing them into core facts;
- store results blindly without checking whether they actually match the user's current context.

Command:

```bash
memos extract "<text>"
```

Common flags:

- `-m, --message`
- `--user-id`
- `--format json|agent`

Example:

```bash
memos extract "User likes coffee and prefers dark mode" --user-id user_123 --format json
```

Working rules:
- `extract` previews candidate memories and does not write them;
- for multi-turn input, compress into core facts before calling the command.
