# `memos search`

Intent map:
- retrieve context before answering -> `memos search`
- do not use `--help` first when the goal is already retrieval

Use this command when:
- the current answer may depend on prior user, project, or conversation context;
- you need semantic retrieval rather than simple browsing;
- you want to find relevant memories before responding or storing new ones.

Never do:
- expand the original user query by pasting an entire long conversation into the search query;
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
- always use the user's original query as the only query for `memos search`;
- do not rewrite, summarize, keyword-compress, retry, or run an additional search query;
- pass `--user-id` when user scope matters;
- do not prepend `memos --help` when `search` is the already known goal.
