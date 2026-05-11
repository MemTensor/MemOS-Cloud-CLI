# MemOS Skill Template Generation Guide

Use this guide when:
- you need to generate a new MemOS skill from the template layer;
- you need to keep `skill-template/` and `skills/` aligned to the same protocol format;
- you need to understand which file owns structure versus executable command guidance.

This directory provides:
- `master-skill-template.md` as the suite-level entry template;
- `skill-template.md` as the single-domain protocol template;
- `domains/*.md` as domain content skeletons.

Always keep:
- `skill-template/` as the structure layer;
- `skills/` as the publishable execution layer;
- shared initialization and output rules centralized in `skills/memos-shared/SKILL.md`.

Directory layout:

```text
skill-template/
├── master-skill-template.md
├── skill-template.md
└── domains/
    ├── config.md
    ├── memory.md
    ├── kb.md
    └── agent.md
```

生成后的实际产物放在：

```text
skills/
├── memos-shared/
├── memos-config/
├── memos-memory/
├── memos-kb/
└── memos-memory-agent/
```

Template responsibilities:

- `master-skill-template.md` is for the top-level suite entry and routing page.
- `skill-template.md` is for a single domain skill such as config, memory, or KB.
- `domains/*.md` hold domain knowledge skeletons and are not published directly as final skills.

Each domain skeleton should cover:
- core concepts;
- resource relationships;
- intent-to-command mapping;
- operational cautions.

Template variables:

`skill-template.md` 中的变量：

- `{{domain}}`：域名，如 `memory`
- `{{meta_description}}`：描述
- `{{title}}`：页面标题，如 `MemOS Memory Protocol`
- `{{service}}`：命令域名，如 `memory`
- `{{use_cases}}`：`Use this skill when` 下的条目
- `{{never_rules}}`：`Never do` 或 `Never store` 下的条目
- `{{command_rows}}`：命令列表
- `{{usage_rules}}`：`Working rules` 下的条目
- `{{workflow_examples}}`：示例命令块

`master-skill-template.md` should preserve:
- suite-level positioning;
- shared skill entry;
- domain skill index;
- domain template index.

Generate a new domain skill:

1. Add a domain skeleton in `domains/`, for example `domains/foo.md`.
2. Copy `skill-template.md`.
3. Replace the frontmatter and protocol placeholders.
4. Output the result to `skills/memos-foo/SKILL.md`.
5. If the domain has concrete commands, add `skills/memos-foo/references/*.md`.
6. Add the new skill to `skills/memos-shared/SKILL.md` and `master-skill-template.md`.

Generate the suite entry:

1. Copy `master-skill-template.md`.
2. Fill in the currently available domain indexes.
3. Output it to the required suite entry document.

Alignment rules:

1. Keep both `skill-template/` and `skills/`.
2. Add or update `domains/` before generating the final skill.
3. Let the template layer own structure and the `skills/` layer own executable command guidance.
4. Centralize shared rules in `skills/memos-shared/SKILL.md`.
5. Domain skills should reference shared setup instead of repeating it.

Non-goals:

- no code generator;
- no template renderer;
- no placeholder validation tool.

If automation is needed later, add it as a separate layer instead of coupling it to the templates now.
