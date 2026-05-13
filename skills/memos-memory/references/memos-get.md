# `memos get`

Use this command when:
- you need retrieval for a specific `user_id`;
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
- `--page`
- `--size`
- `--filter`
- `--include-preference`
- `--include-tool-memory`
- `--format json|markdown`
- `--detail simple|detail`

Example:

```bash
memos get user_123 --format json --detail detail
```
