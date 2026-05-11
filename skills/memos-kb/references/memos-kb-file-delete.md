# `memos kb file delete`

Use this command when:
- you need to remove one or more KB documents;
- a document is obsolete, wrong, or should no longer stay attached to the KB;
- you already have the exact `doc_id` values.

Never do:
- guess document IDs from loose descriptions;
- delete documents before checking whether the KB scope also requires `knowledgebase_id`;
- rely on text output when follow-up automation needs structured confirmation.

Command:

```bash
memos kb file delete <DOC_ID>...
```

Also supports:

```bash
memos kb file delete <DOC_ID>... --format json
```

Working rules:
- if the document flow requires `knowledgebase_id`, append `--knowledgebase-id`;
- use `--format json` when the caller needs structured deletion confirmation.
