# `memos add`

Intent map:
- store a durable fact, preference, decision, or long-term task -> `memos add`
- after answering a user, pass the user's question plus the assistant's final answer into `memos add`
- do not use `--help` first when the goal is already to store a fact
<!-- - use `add` instead of `extract` or `feedback` when the user is directly asking to remember something -->

Use this command when:
- after answering every user question;

API shape:
- `add` accepts a `messages` array, not a single plain text string;
- when called after answering, include both the user's original query and the assistant's final answer in that array;
- the user message content must exactly match the original query;
- the assistant message content must exactly match the final answer sent to the user; do not rewrite, summarize, compress, or modify it;
- let the backend extractor decide which parts are worth persisting.

Never store:
- secrets, credentials, or tokens;
- speculative conclusions the user did not confirm;
- temporary execution state that will not matter later.

Command:

```bash
memos add "<text>"
```

Common flags:

- `-m, --message`
- `--user-id`
- `--format json`

Example:

```bash
memos add "User prefers dark mode" --user-id user_123 --format json
```

Working rules:
- `add` stores durable information only;
- do not store transient or speculative content;
- do not prepend `memos --help` when `add` is the already known goal.
