# `memos search`

Intent map:
- retrieve context at conversation start -> `memos search`
- do not use `--help` first when the goal is already retrieval

Use this command when:
- at conversation start only;
- to retrieve context with the user's original query;
- exactly once per conversation unless the user explicitly asks for another memory operation.
- you need semantic retrieval rather than simple browsing;
- you want to find relevant memories before responding or storing new ones.

Never do:
- expand the original user query by pasting an entire long conversation into the search query;
- run `search` for intermediate states, including planning, partial progress, compact/resume, or continuation after context compaction;
- skip identity fields when user or conversation scope matters;
- use `search` when you already have the exact target records you need.

Example Command:

Do not reuse example parameter values as real parameters. Resolve the query, user id, and knowledge base ids from the current configuration or user-provided context.

```bash
memos search "<query>"
```

Common flags:

- `--user-id`
- `--include-preference`
- `--include-tool-memory`
- `--include-skill-memory`
- `--knowledgebase-ids` JSON array string, such as `'["base123","base456"]'`
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
- at conversation start, must use the user's original query as the only query for `memos search`;
- do not rewrite, summarize, keyword-compress, retry, or run an additional search query;
- do not prepend `memos --help` when `search` is the already known goal.
