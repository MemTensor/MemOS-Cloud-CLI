# Knowledge Base Domain Skeleton

Use this domain when:
- you are generating a knowledge-base-oriented MemOS skill;
- the skill needs to describe KB creation, deletion, and KB document management;
- you want to constrain the skill to documented KB capabilities only.

Never do:
- invent undocumented KB commands, flags, or payload fields;
- assume `kb_id` or `doc_id` shapes without structured output;
- blend KB and memory workflows unless the generated skill explicitly needs both.

Core concepts:
- knowledge base: the KB entity itself.
- knowledge base document: a document resource attached to a knowledge base.
- scope: only cover KB capabilities explicitly documented in the repo.

Resource relationships:

```
Knowledge Base
├── kb create
├── kb delete
└── kb file
    ├── add
    ├── get
    └── delete
```

Intent to command mapping:

- create a knowledge base: `memos kb create`
- delete a knowledge base: `memos kb delete <kb_id>`
- add documents to a knowledge base: `memos kb file add <kb_id> <file>...`
- get a knowledge base document: `memos kb file get <doc_id>`
- delete knowledge base documents: `memos kb file delete <doc_id>...`

Working rules:
- prefer `--format json` whenever later steps must reuse `kb_id` or `doc_id`;
- prefer `--format table` or `--format markdown` for human review flows;
- keep examples aligned with documented parameter shapes in the repo references;
- emphasize that KB features should follow documentation-first constraints.

Example commands:

```bash
memos kb create ... --format json
memos kb delete <kb_id> --format json
memos kb file add <kb_id> <file>... --format json
memos kb file get <doc_id> --format json
memos kb file delete <doc_id>... --format json
```
