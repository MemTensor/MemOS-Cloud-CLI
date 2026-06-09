# `memos kb delete-file`

Intent map:
- delete files from a knowledge base -> `memos kb delete-file`
- remove specific documents from a knowledge base -> `memos kb delete-file`

Use this command when:
- the user wants to remove specific files from a knowledge base without deleting the entire knowledge base;
- outdated or incorrect documents need to be removed.

Command:

```bash
memos kb delete-file --kb-id <KB_ID> --file-ids '<JSON_ARRAY>' --format json
```

Common flags:

- `--kb-id` (required): knowledge base ID
- `--file-ids` (required): JSON array of file ID strings to delete
- `--format json`

Example:

```bash
memos kb delete-file --kb-id kb_abc123 --file-ids '["file_abc123"]' --format json
```

```bash
memos kb delete-file --kb-id kb_abc123 --file-ids '["file_abc123", "file_def456"]' --format json
```

Working rules:
- both `--kb-id` and `--file-ids` are required;
- `--file-ids` must be a valid JSON array of strings;
- this is a destructive operation; confirm with the user if the intent is ambiguous;
- file IDs can be obtained from `memos kb list-file` or `memos kb add-file` responses;
- to remove the entire knowledge base instead, use `memos kb remove`.
