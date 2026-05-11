# Legacy Memory Skill Pointer

Use this file when:
- an older integration still points to `skills/memory_skill.md`;
- you need a backward-compatible entry that redirects to the new skill layout;
- you want a single place to discover the current MemOS skill set.

Never do:
- implement new behavior only in this file;
- treat this file as the primary source of command guidance;
- duplicate full domain instructions here instead of linking to the maintained skills.

Read these skills:
- `skills/memos-shared/SKILL.md` for shared config and runtime rules
- `skills/memos-config/SKILL.md` for setup and config commands
- `skills/memos-memory/SKILL.md` for memory commands such as `extract`, `add`, `search`, `list`, `chat`, `get`, and `delete`
- `skills/memos-kb/SKILL.md` for knowledge base and knowledge base document commands
- `skills/memos-memory-agent/SKILL.md` for retrieve-before-respond and store-after-respond workflow

Recommended entry:
- start with `skills/memos-memory-agent/SKILL.md` for agent automation;
- start with `skills/memos-shared/SKILL.md` if you need setup or runtime conventions first.
