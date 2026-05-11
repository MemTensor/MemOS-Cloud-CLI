# `memos extract`

Use this command when:
- you want to preview memory candidates without storing them;
- the user asks what MemOS would extract from a message;
- you need to inspect candidate memory types before deciding what to save.

Never do:
- treat extracted candidates as already persisted;
- feed long noisy multi-turn transcripts without first compressing them into core facts;
- store results blindly without checking relevance.

Command:

```bash
memos extract -m "<text>"
```

Also supports:

```bash
memos extract "<text>"
```

Common flags:

- `-m, --message`
- `--type`
- `--user-id`
- `--agent-id`
- `--app-id`
- `--run-id`
- `--conversation-id`
- `--format json|agent`

Example:

```bash
memos extract --format json -m "User likes coffee and prefers dark mode" --type memory --type preference --user-id user_123 --conversation-id conv_456
```

Working rules:
- `extract` previews candidate memories and does not write them;
- for multi-turn input, compress into core facts before calling the command.
