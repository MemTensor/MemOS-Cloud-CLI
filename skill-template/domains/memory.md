# Memory Domain Skeleton

Use this domain when:
- you are generating a memory-oriented MemOS skill;
- the skill needs to cover extraction, storage, retrieval, browsing, inspection, deletion, or memory-informed chat;
- you need a domain skeleton for the core memory workflow.

Never do:
- store secrets, credentials, or unconfirmed speculation as memory;
- use `search` when you already have the exact `memory_id`;
- paste raw long-form dialogue into queries without compressing it first.

Core concepts:
- `extract`: preview candidate memories without writing them.
- `add`: write text or messages into memory.
- `search`: semantically retrieve relevant memories.
- `list`: browse saved memories without semantic retrieval.
- `get / delete`: read or remove a memory by exact `memory_id`.
- `chat`: answer with MemOS-backed memory context.

Resource relationships:

```
Memory Workflow
├── extract
├── add
├── search
├── list
├── get
├── delete
└── chat
```

Intent to command mapping:

- preview extracted candidates: `memos extract`
- store a durable fact or preference: `memos add`
- retrieve relevant memories semantically: `memos search`
- browse existing memories: `memos list`
- inspect one memory by ID: `memos get <id>`
- delete one memory by ID: `memos delete <id>`
- answer with memory support: `memos chat`

Working rules:
- use `--format json` whenever a later step must parse exact fields or IDs;
- use `--format agent` when retrieved memory should be injected back into model context;
- if you already have a `memory_id`, prefer `get` or `delete` directly;
- compress search queries into keywords, entities, preferences, and intent;
- keep the distinction between `extract` and `add` explicit in generated skills.

Example commands:

```bash
memos extract --format json -m "<message>" --user-id <USER_ID> --conversation-id <CONV_ID>
memos add --format json -m "<fact>" --user-id <USER_ID> --conversation-id <CONV_ID>
memos search --format agent --detail simple -q "<query>" --user-id <USER_ID> --conversation-id <CONV_ID>
memos list --format table --detail simple --user-id <USER_ID>
memos get <MEMORY_ID> --format json --detail detail
memos delete <MEMORY_ID> --format json
memos chat --format agent -q "<query>" --user-id <USER_ID> --conversation-id <CONV_ID>
```
