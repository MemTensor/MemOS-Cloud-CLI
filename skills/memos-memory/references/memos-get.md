# `memos get`

Intent map:
- fetch memories by `user_id` -> `memos get`
- do not use `--help` first when the goal is already to fetch scoped records

Use this command when:
- you need retrieval by a specific `user_id`;
- you want to inspect returned memory records in detail;
- you want raw official JSON from the documented `get_memory` API.

Never do:
- assume you can fetch by `memory_id` through `get`;
- assume the record content from prior summaries without reading the API result;
- skip structured output if a later step depends on exact fields.

Command:

```bash
memos get <USER_ID>
```

Common flags:

- `[USER_ID]`
- `--user-id`
- `--conversation-id`
- `--page`
- `--size`
- `--filter`
- `--include-preference`
- `--include-tool-memory`
- `--format json|markdown`
- `--detail simple|detail`

Example:

```bash
memos get user_123 --conversation-id conv_001 --format json --detail detail
```

Working rules:
- `get` returns scoped records for the requested `user_id` and `conversation_id`;
- when `--conversation-id` is omitted, the CLI uses the configured `defaults.conversation_id`; pass the same conversation used by `memos add` so reads see the records just written;
- `memos list` is an alias of `memos get` and accepts the same flags;
- do not prepend `memos --help` when `get` is the already known goal.
