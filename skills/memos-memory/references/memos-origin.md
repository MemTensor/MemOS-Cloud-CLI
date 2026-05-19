# `memos origin`

Use `memos origin` when you already have a concrete `memory_id` and need the original source messages or source text behind that memory.

Example:

```bash
memos origin <MEMORY_ID>
memos origin <MEMORY_ID> --detail simple
memos origin <MEMORY_ID> --detail detail
memos origin <MEMORY_ID> --format markdown --detail detail
memos origin <MEMORY_ID> --format json
```

Behavior:

- calls the official `GET /v1/get/memory/{memid}` route;
- supports `--format table|markdown|agent|json`;
- supports `--detail simple|detail`;
- `simple` shows the memory summary and source content;
- `detail` shows the memory summary plus source type, role, time, language, and source content;
- source messages are read from `data.metadata.sources`;
- use `--format json` when later steps need the raw response payload.
