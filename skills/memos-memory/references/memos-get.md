# `memos get`

Use this command when:
- you already have a concrete `memory_id`;
- you need to inspect one memory record in detail;
- you want to verify a record before deciding whether to delete it.

Never do:
- search by guess when the ID is already known;
- assume the record content from prior summaries without reading the source record;
- skip structured output if a later step depends on exact fields.

Command:

```bash
memos get <MEMORY_ID>
```

Common flags:

- `--user-id`
- `--format json|markdown`
- `--detail simple|detail`

Example:

```bash
memos get mem_123456 --format json --detail detail
```
