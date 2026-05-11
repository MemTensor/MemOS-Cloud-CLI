---
name: memos-suite
description: Use this skill as the MemOS CLI entry point to choose the right shared, memory, config, knowledge base, or agent workflow skill.
---

# MemOS Suite Protocol

Use this skill when:
- you need a top-level entry point for MemOS CLI capabilities;
- you are choosing which domain skill to load for the current task;
- you need to route between shared rules, memory operations, KB operations, and automation workflows.

Always apply:
- read the shared skill before domain-specific commands;
- prefer `--format json` when later steps must parse IDs or structured output;
- prefer `--format agent` when retrieved context will be injected back into the model;
- pass `--user-id`, `--conversation-id`, and other stable identity fields when the framework provides them.

Read these skills:
- [`../skills/memos-shared/SKILL.md`](../skills/memos-shared/SKILL.md) — initialization, config, identity, and output conventions
- [`../skills/memos-memory/SKILL.md`](../skills/memos-memory/SKILL.md) — extract, add, search, list, chat, get, and delete memory
- [`../skills/memos-kb/SKILL.md`](../skills/memos-kb/SKILL.md) — knowledge bases and knowledge base documents
- [`../skills/memos-memory-agent/SKILL.md`](../skills/memos-memory-agent/SKILL.md) — retrieve-before-respond and store-after-respond workflow

Template sources:

- [`./domains/config.md`](./domains/config.md)
- [`./domains/memory.md`](./domains/memory.md)
- [`./domains/kb.md`](./domains/kb.md)
- [`./domains/agent.md`](./domains/agent.md)
- [`./generation-guide.md`](./generation-guide.md)

Command discovery:

```bash
memos --help
memos config --help
memos kb --help
```
