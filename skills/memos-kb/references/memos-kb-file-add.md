# `memos kb file add`

Use this command when:
- you need to attach one or more documents to a knowledge base;
- the workflow is preparing KB content for later retrieval;
- you already know the target `knowledgebase_id`.

Never do:
- assume unsupported file types will be accepted;
- omit `--format json` when the next step needs returned document IDs;
- pass undocumented payload shapes instead of the documented file list form.

Command:

```bash
memos kb file add <KNOWLEDGEBASE_ID> <FILE_URL>...
```

Also supports:

```bash
memos kb file add <KNOWLEDGEBASE_ID> <FILE_URL>... --format json
```

Working rules:
- the CLI currently accepts URL or path lists as input;
- supported file types should follow CLI validation;
- use `--format json` when later steps need document IDs.
