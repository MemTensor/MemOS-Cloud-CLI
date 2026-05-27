---
name: memos-memory
description: Use MemOS to extract, retrieve, persist, inspect, and delete long-term memory for user, project, and task context.
---

# MemOS Memory Protocol

Command selection rules:
- if the user wants the model to remember a durable fact or preference, use `memos add` directly;
- if the user wants to preview what would be stored, use `memos extract` directly;
- if the user wants context retrieval before answering, use `memos search` directly;
- if the user wants a memory-aware response from MemOS itself, use `memos chat` directly;
- if the user already has a concrete memory id, use `memos get`, `memos origin`, or `memos delete` directly;
- do not call `memos --help` by default when the intent already matches one of the commands below;
- use `memos --help` only when the command name, parameters, or route are genuinely unclear;
- do not use `memos init` as a discovery step when the CLI is already installed.

Identity rules:
- always prefer the exact configured `user_id` value when a command is scoped by user;
- do not shorten, normalize, or replace the configured `user_id` (for example, `locomo_exp_user_0` must stay exactly as-is);
- use `--user-id` explicitly on every scoped memory command when the user scope matters.

Hard mapping:
- store a durable fact, preference, decision, or long-term task -> `memos add`
- preview candidate memories before storing -> `memos extract`
- retrieve context before answering -> `memos search`
- ask MemOS to answer with memory context -> `memos chat`
- fetch memories by user_id -> `memos get`
- trace where one memory came from -> `memos origin`
- remove one concrete memory by id -> `memos delete`
- delete all memories for a user_id -> `memos delete --user-id`

Use this skill when:
- the task may depend on prior user, project, or conversation context;
- the user provides a stable new fact, preference, or background detail;
- you want to preview extracted memory candidates before storing them;
- you need to inspect, list, delete, or trace the source of an existing memory record.

Never store:
- secrets, API keys, tokens, or passwords;
- unverified guesses or speculative conclusions as user facts;
- short-lived task state that will not matter in future sessions;
- redundant paraphrases when one concise factual memory is enough.

Use these commands:
- `memos add "<fact>" --user-id <USER_ID> --format json`
- `memos extract "<message>" --user-id <USER_ID> --format json`
- `memos search "<query>" --user-id <USER_ID> --format agent --detail simple`
- `memos chat "<message>" --user-id <USER_ID> --format agent`
- `memos get <USER_ID> --format json --detail detail`
- `memos origin <MEMORY_ID> --format json`
- `memos delete <MEMORY_ID> --format json`
- `memos delete --user-id <USER_ID> --format json`

Choose commands by intent:
- use [`./references/memos-add.md`](./references/memos-add.md) when the user gives a durable fact or preference worth saving;
- use [`./references/memos-extract.md`](./references/memos-extract.md) when the user wants a preview of memory candidates without storing;
- use [`./references/memos-search.md`](./references/memos-search.md) before answering when historical context may matter;
- use [`./references/memos-chat.md`](./references/memos-chat.md) when interacting with MemOS chat capability directly;
- use [`./references/memos-get.md`](./references/memos-get.md) for retrieval by `user_id`;
- use [`./references/memos-origin.md`](./references/memos-origin.md) when you need the original source messages behind a specific memory;
- use [`./references/memos-delete.md`](./references/memos-delete.md) only when you already have a concrete `memory_id`.

Process rules:
- the default workflow is: search before answering, answer second, then add after answering;
- when you add after answering, pass both the user's question and the assistant's final answer into `memos add` so the extractor can decide what is worth keeping;
- do not skip `add` just because the current turn does not obviously contain a durable fact;
- per turn, keep memory-tool usage bounded: at most 1 original-query `search` call and at most 1 `add` call after answering;
- do not chain additional memory tools in the same turn unless the user explicitly asks for that specific operation;
- `extract` is only for previewing candidates, not for storing;
- `feedback` is a separate command and should only be used when the user explicitly wants feedback storage;
- if the user’s message is already a memory write request, prefer `add` over `feedback` or `extract`.
- do not start a memory-write request by checking config or running `memos init`;
- if the user says "remember these messages", "save these messages", or equivalent, go directly to `memos add` with the exact configured `user_id`.

Intent map:
- preview what would be stored -> `memos extract`
- retrieve context before answering -> `memos search`
- store after answering -> `memos add`
- get memories by `user_id` -> `memos get`
- trace where a memory came from -> `memos origin`
- delete one concrete memory -> `memos delete`
- delete all memories for a `user_id` -> `memos delete --user-id`
- ask MemOS to answer with memory context -> `memos chat`

Working rules:
- always use the user's original query as the only query for `memos search`;
- do not rewrite, summarize, keyword-compress, retry, or run an additional search query;
- `memos add` uses a `messages` array payload; when adding after a turn, include both the user's question and the assistant's answer in that array;
- when `--format` is omitted, treat the default as `agent`;
- append `--format json` at the end of the command whenever a later step needs exact `memory_id` or structured records;
- append `--format agent` at the end of the command when the result will be injected back into model context;
- keep `--format` at the end of every command line, and keep `--detail` at the end only for `search` and `get`;
- do not run `memos init` as a default preflight step if MemOS CLI is already installed;
- only run `memos init --agent <current_agent>` when the CLI is missing and the user has explicitly provided an API key or asked to initialize MemOS;
- if initialization is needed but no API key is available, ask the user for the key instead of stopping the workflow;
- the active agent should initialize itself with its own `--agent` value, not a hardcoded different agent name;
- prefer stable identity fields such as `--user-id` when available;
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
