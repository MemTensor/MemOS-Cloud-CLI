# `memos delete`

Intent map:
- remove one concrete memory by id -> `memos delete`
- do not use `--help` first when the memory id is already known

Use this command when:
- the user explicitly asks to delete a memory;
- a memory is confirmed to be wrong, expired, or should no longer be retained;
- you already have the exact `memory_id`.

Never do:
- guess `memory_id`;
- delete based on a vague description without first checking the exact record;
- remove memories just because they look uncertain unless the user or evidence confirms they are wrong.

Command:

```bash
memos delete <MEMORY_ID>
```

Common flags:

- `--format json`

Example:

```bash
memos delete mem_123456 --format json
```

Working rules:
- confirm the `memory_id` before deletion;
- if context is fuzzy, use `get` or `search` first instead of deleting by guess.
- do not prepend `memos --help` when `delete` is the already known goal.
