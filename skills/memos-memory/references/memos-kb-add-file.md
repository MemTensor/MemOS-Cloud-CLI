# `memos kb add-file`

Intent map:
- upload documents to a knowledge base -> `memos kb add-file`
- add a URL or text content to a knowledge base -> `memos kb add-file`

Use this command when:
- the user wants to add documents (URLs or raw text) to an existing knowledge base;
- new reference material needs to be indexed for retrieval.

Command:

```bash
memos kb add-file --kb-id <KB_ID> --files '<JSON_ARRAY>' --format json
```

Common flags:

- `--kb-id` (required): target knowledge base ID
- `--files` (required): JSON array of file entries
- `--format json`

The `--files` parameter accepts a JSON array where each element is either:
- a URL string: `"https://example.com/doc.pdf"`
- an object with content: `{"content": "raw text content here"}`

Example:

```bash
memos kb add-file --kb-id kb_abc123 --files '["https://example.com/doc.pdf"]' --format json
```

```bash
memos kb add-file --kb-id kb_abc123 --files '[{"content": "This is the document text content."}]' --format json
```

Working rules:
- `--kb-id` and `--files` are both required;
- `--files` must be a valid JSON array; wrap the value in single quotes to prevent shell interpretation;
- the response contains `file_id` values needed to track processing status via `memos kb get-file`;
- file processing is asynchronous; use `memos kb get-file` to check completion status.
