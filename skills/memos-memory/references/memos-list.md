# `memos list`

Use this command when:
- you want to browse existing memories rather than run semantic retrieval;
- you need a recent or limited slice of saved memories;
- you need to inspect records before choosing one for a follow-up action.

Never do:
- use `list` as a substitute for semantic search when the query is topic-specific;
- rely on text output when a later step must parse IDs;
- assume the first listed record is the right one without checking.

Command:

```bash
memos list
```

Common flags:

- `--user-id`
- `-n, --limit`
- `--format table|markdown|agent|json`
- `--detail simple|detail`

Example:

```bash
memos list --format table --detail simple --user-id user_123 -n 20
```

Working rules:
- `list` is for browsing, not semantic retrieval;
- prefer `--format json` when you need exact IDs for a later step.
