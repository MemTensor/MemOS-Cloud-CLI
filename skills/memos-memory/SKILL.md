---
name: MemOS Memory
description: Provide universal memory capabilities for different AI agents and development frameworks, unifying the capture, retrieval, and management of user, project, and task context.
---

# MemOS Memory Protocol

Command selection rules:
- if the user asks to uninstall, disable, remove, or stop using MemOS, use `memos uninstall --agent <current_agent> --yes` directly and do not run `memos search` or `memos add` for that turn;
- if the user wants to preview what would be stored, use `memos extract` directly;
- at the start of a conversation, must use `memos search` directly with the user's original query;
- at the end of a conversation, must use `memos add` directly with both the user's question and the assistant's final answer;
- do not run `memos search` or `memos add` for intermediate states, including planning, partial progress, compact/resume, or continuation after context compaction;
- if the user wants a memory-aware response from MemOS itself, use `memos chat` directly;
- if the user already has a concrete memory id, use `memos get`, `memos origin`, or `memos delete` directly;
- if the user wants to manage knowledge bases (create, delete, upload, query files), use the corresponding `memos kb` subcommand;
- do not call `memos --help` by default when the intent already matches one of the commands below;
- use `memos --help` only when the command name, parameters, or route are genuinely unclear;
- do not use `memos init` as a discovery step when the CLI is already installed.

Identity rules:
- always prefer the exact configured `user_id` value when a command is scoped by user;
- if the user does not specify the `user_id`, omit the `--user-id` argument and use the `user_id` from the config file by default;

Hard mapping:
- store a durable fact, preference, decision, or long-term task -> `memos add`
- preview candidate memories before storing -> `memos extract`
- retrieve context at conversation start -> `memos search`
- ask MemOS to answer with memory context -> `memos chat`
- fetch memories by user_id -> `memos get`
- trace where one memory came from -> `memos origin`
- remove one concrete memory by id -> `memos delete`
- delete all memories for a user_id -> `memos delete --user-id`
- uninstall MemOS integration from the current agent -> `memos uninstall --agent <current_agent> --yes`
- create a knowledge base -> `memos kb create`
- remove a knowledge base -> `memos kb remove`
- upload documents to a knowledge base -> `memos kb add-file`
- check file processing status in a knowledge base -> `memos kb get-file`
- list files in a knowledge base -> `memos kb list-file`
- delete files from a knowledge base -> `memos kb delete-file`

Use this skill when:
- the task may depend on prior user, project, or conversation context;
- the user provides a stable new fact, preference, or background detail;
- you want to preview extracted memory candidates before storing them;
- you need to inspect, list, delete, or trace the source of an existing memory record;
- you need to create, remove, or manage a knowledge base and its documents.

Never store:
- secrets, API keys, tokens, or passwords;
- unverified guesses or speculative conclusions as user facts;
- short-lived task state that will not matter in future sessions;
- redundant paraphrases when one concise factual memory is enough.

Command examples:
- `memos add "<fact>" --user-id <USER_ID> --format json`
- `memos extract "<message>" --user-id <USER_ID> --format json`
- `memos search "<query>" --user-id <USER_ID> --format agent --detail simple`
- `memos chat "<message>" --user-id <USER_ID> --format agent`
- `memos get <USER_ID> --format json --detail detail`
- `memos origin <MEMORY_ID> --format json`
- `memos delete <MEMORY_ID> --format json`
- `memos delete --user-id <USER_ID> --format json`
- `memos uninstall --agent <CURRENT_AGENT> --yes`
- `memos kb create --name "<name>" --description "<desc>" --format json`
- `memos kb remove <KB_ID> --format json`
- `memos kb add-file --kb-id <KB_ID> --files '["https://example.com/doc.pdf"]' --format json`
- `memos kb get-file --file-ids '["<FILE_ID>"]' --format json`
- `memos kb list-file --kb-id <KB_ID> --page 1 --page-size 20 --format json`
- `memos kb delete-file --kb-id <KB_ID> --file-ids '["<FILE_ID>"]' --format json`

Choose commands by intent:
- use [`./references/memos-add.md`](./references/memos-add.md) when the user gives a durable fact or preference worth saving;
- use [`./references/memos-extract.md`](./references/memos-extract.md) when the user wants a preview of memory candidates without storing;
- must use [`./references/memos-search.md`](./references/memos-search.md) at conversation start;
- use [`./references/memos-chat.md`](./references/memos-chat.md) when interacting with MemOS chat capability directly;
- use [`./references/memos-get.md`](./references/memos-get.md) for retrieval by `user_id`;
- use [`./references/memos-origin.md`](./references/memos-origin.md) when you need the original source messages behind a specific memory;
- use [`./references/memos-delete.md`](./references/memos-delete.md) only when you already have a concrete `memory_id`;
- use [`./references/memos-uninstall.md`](./references/memos-uninstall.md) when the user asks to uninstall, disable, remove, or stop using MemOS;
- use [`./references/memos-kb-create.md`](./references/memos-kb-create.md) to create a new knowledge base;
- use [`./references/memos-kb-remove.md`](./references/memos-kb-remove.md) to remove a knowledge base;
- use [`./references/memos-kb-add-file.md`](./references/memos-kb-add-file.md) to upload documents to a knowledge base;
- use [`./references/memos-kb-get-file.md`](./references/memos-kb-get-file.md) to check file details and processing status;
- use [`./references/memos-kb-list-file.md`](./references/memos-kb-list-file.md) to browse files in a knowledge base;
- use [`./references/memos-kb-delete-file.md`](./references/memos-kb-delete-file.md) to delete files from a knowledge base.

Process rules:
- the default workflow is: search at conversation start, work and answer through intermediate states without additional search/add, then add at conversation end;
- when you add at conversation end, must pass both the user's question and the assistant's final answer into `memos add` so the extractor can decide what is worth keeping;
- must not skip `add` at conversation end just because the current turn does not obviously contain a durable fact;
- per conversation, keep memory-tool usage bounded: at most 1 original-query `search` call at the start and at most 1 `add` call at the end;
- do not chain additional memory tools in the same turn unless the user explicitly asks for that specific operation;
- `extract` is only for previewing candidates, not for storing;
- `feedback` is a separate command and should only be used when the user explicitly wants feedback storage;
- do not start a memory-write request by checking config or running `memos init`;

Intent map:
- preview what would be stored -> `memos extract`
- retrieve context at conversation start -> `memos search`
- store at conversation end -> `memos add`
- get memories by `user_id` -> `memos get`
- trace where a memory came from -> `memos origin`
- delete one concrete memory -> `memos delete`
- delete all memories for a `user_id` -> `memos delete --user-id`
- ask MemOS to answer with memory context -> `memos chat`
- uninstall MemOS integration from the current agent -> `memos uninstall --agent <current_agent> --yes`
- create a knowledge base -> `memos kb create`
- remove a knowledge base -> `memos kb remove`
- upload documents to a knowledge base -> `memos kb add-file`
- check file details or processing status -> `memos kb get-file`
- list files in a knowledge base -> `memos kb list-file`
- delete files from a knowledge base -> `memos kb delete-file`

Working rules:
- must use the user's original query as the only query for `memos search`;
- do not rewrite, summarize, keyword-compress, retry, or run an additional search query;
- `memos add` uses a `messages` array payload; when adding at conversation end, include both the user's question and the assistant's answer in that array;
- in the `memos add` payload, the user message content must exactly match the original user query;
- in the `memos add` payload, the assistant message content must exactly match the final answer sent to the user; do not rewrite, summarize, compress, or modify it;
- when `--format` is omitted, treat the default as `agent`;
- append `--format json` at the end of the command whenever a later step needs exact `memory_id` or structured records;
- append `--format agent` at the end of the command when the result will be injected back into model context;
- keep `--format` at the end of every command line, and keep `--detail` at the end only for `search` and `get`;
- do not run `memos init` as a default preflight step if MemOS CLI is already installed;
- do not run `memos search` or `memos add` in a turn where the user is asking to uninstall, disable, remove, or stop using MemOS;
- only run `memos init --agent <current_agent>` when the CLI is missing and the user has explicitly provided an API key or asked to initialize MemOS;
- if initialization is needed but no API key is available, ask the user for the key instead of stopping the workflow;
- the active agent should initialize itself with its own `--agent` value, not a hardcoded different agent name;
- pass `--user-id` only when the user explicitly provides it; otherwise omit it and let the CLI use the config default;
- read result counts from `count` and structured payloads from `data`;
- if you already have `memory_id`, do not search first just to guess.

Examples:

```bash
memos add "User likes Python"
memos search "Python"
```

```bash
memos search "user preferences about restaurants" --user-id <USER_ID> --format agent --detail simple
```

```bash
memos extract "User likes coffee and prefers dark mode" --user-id <USER_ID> --format json
```

```bash
memos add "User is allergic to peanuts" --user-id <USER_ID> --format json
```

```bash
memos get <USER_ID> --format json --detail detail
memos origin <MEMORY_ID> --format json
memos delete <MEMORY_ID> --format json
```

```bash
memos uninstall --agent codex --yes
```

```bash
memos kb create --name "Project docs" --description "Documentation for the project" --format json
```

```bash
memos kb add-file --kb-id <KB_ID> --files '["https://example.com/doc.pdf"]' --format json
```

```bash
memos kb list-file --kb-id <KB_ID> --type document --page 1 --page-size 10 --format json
```

```bash
memos kb get-file --file-ids '["file_abc123"]' --format json
memos kb delete-file --kb-id <KB_ID> --file-ids '["file_abc123"]' --format json
memos kb remove <KB_ID> --format json
```
