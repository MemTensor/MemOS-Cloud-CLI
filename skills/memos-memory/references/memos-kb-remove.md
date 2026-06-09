# `memos kb remove`

Intent map:
- remove a knowledge base -> `memos kb remove`
- delete an entire knowledge base and its contents -> `memos kb remove`

Use this command when:
- the user wants to permanently delete a knowledge base;
- a knowledge base is no longer needed.

Command:

```bash
memos kb remove <KB_ID> --format json
```

Common flags:

- `<KB_ID>` (required, positional): the knowledge base ID to remove
- `--format json`

Example:

```bash
memos kb remove kb_abc123 --format json
```

Working rules:
- this is a destructive operation; confirm with the user before executing if the intent is ambiguous;
- requires a valid `knowledgebase_id` obtained from `memos kb create` or `memos kb list-file`;
- all files within the knowledge base will be removed along with it.
