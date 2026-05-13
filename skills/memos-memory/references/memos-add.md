# `memos add`

Use this command when:
- the user states a durable preference, fact, or background detail;
- the conversation produces a memory likely to help future turns;
- you already know the memory should be stored, not just previewed.

Never store:
- secrets, credentials, or tokens;
- speculative conclusions the user did not confirm;
- temporary execution state that will not matter later.

Command:

```bash
memos add "<text>"
```

Common flags:

- `-m, --message`
- `--user-id`
- `--format json`

Example:

```bash
memos add "User prefers dark mode" --user-id user_123 --format json
```
