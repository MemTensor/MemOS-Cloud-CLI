# `memos kb get-file`

Intent map:
- check file processing status -> `memos kb get-file`
- get file details from a knowledge base -> `memos kb get-file`

Use this command when:
- the user wants to check whether uploaded files have been processed;
- you need to verify file details (name, type, status) after uploading.

Command:

```bash
memos kb get-file --file-ids '<JSON_ARRAY>' --format json
```

Common flags:

- `--file-ids` (required): JSON array of file ID strings
- `--format json`

Example:

```bash
memos kb get-file --file-ids '["file_abc123", "file_def456"]' --format json
```

Working rules:
- `--file-ids` is required and must be a valid JSON array of strings;
- file IDs are obtained from the response of `memos kb add-file` or `memos kb list-file`;
- the response includes processing status for each file (e.g., pending, processing, completed, failed);
- use this command after `add-file` to confirm documents are ready for retrieval.
