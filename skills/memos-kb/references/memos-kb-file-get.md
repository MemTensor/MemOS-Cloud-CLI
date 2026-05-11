# `memos kb file get`

Use this command when:
- you need to inspect one KB document by exact ID;
- you want to verify a document before deciding on deletion or replacement;
- the workflow already has the concrete `doc_id`.

Never do:
- search by guess when the exact `doc_id` is already known;
- rely on summary text if later steps need exact document fields;
- assume the returned shape without using a machine-readable format.

Command:

```bash
memos kb file get <DOC_ID>
```

Also supports:

```bash
memos kb file get <DOC_ID> --format json
```

Working rules:
- use it to fetch a single KB document by ID;
- prefer `--format json` when later steps need to continue operating on the document.
