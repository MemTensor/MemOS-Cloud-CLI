# `memos search`

Intent map:
- without the native hook, retrieve context at conversation start -> `memos search`
- with the native hook, retrieve additional context when injected memory is missing or insufficient -> `memos search`
- do not use `--help` first when the goal is already retrieval

Use this command when:
- without the native hook, at conversation start only;
- without the native hook, to retrieve context with the user's original query;
- with the native hook, only when `<memos_memory_context>` is missing, insufficient, ambiguous, or clearly unrelated and more memory context would materially help the answer;
- with a native hook that already injects search results, supplemental lookup must use a rewritten, focused query that targets the missing memory context;
- with an add-only setup such as Cursor's native hook mode here, the hook has not searched the prompt yet, so the first lookup may use the original user query;
- you need semantic retrieval rather than simple browsing;
- you want to find relevant memories before responding.

Never do:
- run `search` automatically just because a new turn started while the native hook is active;
- run `search` again when injected memory is already sufficient;
- in native hook mode, reuse the original user prompt verbatim for supplemental lookup;
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
- without the native hook, at conversation start, use the user's original query as the only query for `memos search`;
- with a native hook that already injects search results, use a rewritten, focused query only when the injected memory is not enough for the current answer;
- with an add-only hook setup, use the original query first when you are still gathering the first relevant memory context;
- in native hook mode, the query should describe what is missing, while preserving exact names, file paths, project names, error messages, memory IDs, or user-provided terms that matter;
- do not rewrite, summarize, keyword-compress, retry, or run an additional search query unless the user explicitly asks for another memory operation or the injected memory is insufficient under native hook mode;
- do not prepend `memos --help` when `search` is the already known goal.
