# `memos kb create`

Use this command when:
- you need to create a new knowledge base;
- the workflow must capture a fresh `kb_id` for later document operations;
- you are initializing a KB-backed project context.

Never do:
- create duplicate knowledge bases without checking naming intent first;
- rely on text output if a later step must parse the returned `kb_id`;
- invent undocumented creation flags.

Command:

```bash
memos kb create "<name>"
```

Also supports:

```bash
memos kb create "<name>" --description "<desc>" --format json
```

Working rules:
- use `--format json` when the next step needs the returned `kb_id`;
- record the created knowledge base ID after success.
