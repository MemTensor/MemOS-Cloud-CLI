# `memos search`

Use this command when:
- the current answer may depend on prior user, project, or conversation context;
- you need semantic retrieval rather than simple browsing;
- you want to find relevant memories before responding or storing new ones.

Never do:
- paste an entire long conversation as the raw query;
- skip identity fields when user or conversation scope matters;
- use `search` when you already have the exact `memory_id`.

Command:

```bash
memos search -q "<query>"
```

Also supports:

```bash
memos search "<query>"
```

Common flags:

- `-q, --query`
- `-n, --limit`
- `--user-id`
- `--agent-id`
- `--app-id`
- `--run-id`
- `--conversation-id`
- `--format table|markdown|agent|json`
- `--detail simple|detail`

Example:

```bash
memos search --format agent --detail simple -q "restaurants food preferences" --user-id user_123 --conversation-id conv_456
```

Working rules:
- use compressed keywords instead of raw long-form dialogue;
- prioritize user preferences, entities, and topic terms in the query;
- when both user and conversation identity exist, pass both.
