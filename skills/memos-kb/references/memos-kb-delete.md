# `memos kb delete`

Use this command when:
- you need to remove a knowledge base;
- the KB is confirmed to be obsolete or created by mistake;
- you already have the exact `knowledgebase_id`.

Never do:
- guess the `knowledgebase_id`;
- delete a KB from a vague description without confirming the exact target;
- skip machine-readable output if downstream cleanup depends on structured confirmation.

Command:

```bash
memos kb delete <KNOWLEDGEBASE_ID>
```

Also supports:

```bash
memos kb delete <KNOWLEDGEBASE_ID> --format json
```

Working rules:
- confirm the `knowledgebase_id` before deletion.
