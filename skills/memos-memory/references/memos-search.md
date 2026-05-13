# `memos search`

Use this command when:
- the current answer may depend on prior user, project, or conversation context;
- you need semantic retrieval rather than simple browsing;
- you want to find relevant memories before responding or storing new ones.

Never do:
- paste an entire long conversation as the raw query;
- skip identity fields when user or conversation scope matters;
- use `search` when you already have the exact target records you need.

Command:

```bash
memos search "<query>"
```

Common flags:

- `--user-id`
- `--include-preference`
- `--include-tool-memory`
- `--include-skill-memory`
- `--memory-limit-number`
- `--preference-limit-number`
- `--tool-memory-limit-number`
- `--skill-memory-limit-number`
- `--format table|markdown|agent|json`
- `--detail simple|detail`

Example:

```bash
memos search "restaurants food preferences" --user-id user_123 --format agent --detail simple
```

Working rules:
- use compressed keywords instead of raw long-form dialogue;
- prioritize user preferences, entities, and topic terms in the query;
- pass `--user-id` when user scope matters.
