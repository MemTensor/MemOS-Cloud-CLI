# `memos kb list-file`

Intent map:
- list files in a knowledge base -> `memos kb list-file`
- browse knowledge base documents -> `memos kb list-file`

Use this command when:
- the user wants to see what files are in a knowledge base;
- you need to find file IDs for subsequent get-file or delete-file operations;
- paginating through a large knowledge base.

Command:

```bash
memos kb list-file --kb-id <KB_ID> --format json
```

Common flags:

- `--kb-id` (required): knowledge base ID
- `--type`: filter by file type (`document` or `skill`)
- `--page`: page number (default: 1)
- `--page-size`: items per page (default: 20)
- `--format json`

Example:

```bash
memos kb list-file --kb-id kb_abc123 --format json
```

```bash
memos kb list-file --kb-id kb_abc123 --type document --page 2 --page-size 10 --format json
```

Working rules:
- `--kb-id` is required;
- use `--type` to filter results when the knowledge base contains both documents and skills;
- the response includes pagination metadata (total count, current page);
- file IDs from the response can be used with `memos kb get-file` or `memos kb delete-file`.
