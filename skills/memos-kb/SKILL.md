---
name: memos-kb
description: Use MemOS knowledge base commands to create, delete, and manage knowledge base documents with documented CLI capabilities only.
---

# MemOS Knowledge Base Protocol

Read first:
- [`../memos-shared/SKILL.md`](../memos-shared/SKILL.md)

Use this skill when:
- you need to create or remove a knowledge base;
- you need to add, inspect, or delete a knowledge base document;
- the task requires documented KB features rather than inferred or hidden CLI behavior.

Never do:
- rely on undocumented KB flags or payload fields;
- assume an ID shape without reading structured output first;
- mix KB document flows with memory flows unless the task explicitly needs both.

Use these commands:
- `memos kb create ...`
- `memos kb delete ...`
- `memos kb file add ...`
- `memos kb file get ...`
- `memos kb file delete ...`

References:
- [`./references/memos-kb-create.md`](./references/memos-kb-create.md)
- [`./references/memos-kb-delete.md`](./references/memos-kb-delete.md)
- [`./references/memos-kb-file-add.md`](./references/memos-kb-file-add.md)
- [`./references/memos-kb-file-get.md`](./references/memos-kb-file-get.md)
- [`./references/memos-kb-file-delete.md`](./references/memos-kb-file-delete.md)

Working rules:
- use only KB capabilities that are explicitly documented in the repo references;
- append `--format json` at the end of the command for any step that must parse IDs or structured results later;
- append `--format table` or `--format markdown` at the end of the command for human review of KB results;
- follow the parameter shapes shown in the reference docs instead of inventing extra fields.
