# MemOS CLI

Universal memory interface for AI agents.

## Project Structure

```
MemOS-CLI/
├── src/memos_cli/
│   ├── __init__.py          # Package version
│   ├── __main__.py          # python -m memos_cli entry
│   ├── main.py              # Main CLI app (Typer)
│   ├── config.py            # Configuration management
│   ├── output.py            # Output formatting (text/json)
│   ├── branding.py          # Brand colors and symbols
│   ├── state.py             # State management (agent mode)
│   ├── telemetry.py         # Telemetry reporting
│   ├── backend/             # API backend layer
│   │   ├── base.py          # Abstract base class
│   │   └── memos_api.py     # MemOS Cloud API implementation
│   └── commands/            # CLI commands
│       ├── init.py          # memos init
│       ├── config_cmd.py    # memos config (show/get/set)
│       └── memory.py        # add/search/get/origin/delete/extract/rerank/feedback/chat
├── skills/
│   ├── memos-memory/        # Memory domain skill (P0 commands)
│   │   ├── SKILL.md         # Skill entry and usage protocol
│   │   └── references/      # Skill reference docs
│   │       ├── memos-add.md
│   │       ├── memos-chat.md
│   │       ├── memos-delete.md
│   │       ├── memos-extract.md
│   │       ├── memos-get.md
│   │       └── memos-search.md
├── pyproject.toml
├── package.json
├── bin/
│   └── memos.js            # npm launcher
├── scripts/
│   └── postinstall.js      # npm binary installer
├── npm/
│   └── README.md           # npm binary payload directory
└── README.md
```

## Installation

### End Users

```bash
npm install -g @memos/cli
```

The npm package downloads a prebuilt MemOS CLI binary for the current platform during installation, so end users do not need a local Python environment.

Expected binary targets:
- `darwin-arm64`
- `darwin-x64`
- `linux-x64`
- `windows-x64`

### Development

```bash
pip install -e .
```

## Quick Start

### 1. Initialize

```bash
memos init --agent codex
```

This command installs the bundled MemOS operation skill to the explicitly selected agent skills directory.
`--agent` is required, and installation to a generic global directory is not supported.
It also installs shell completion automatically for the current shell when shell detection succeeds.

Supported targets:
- `--agent codex` → `~/.codex/skills/memos/`
- `--agent cursor` → `~/.cursor/skills/memos/`
- `--agent claude` → `~/.claude/skills/memos/`
- `--agent openclaw` → `~/.openclaw/skills/memos/`
- `--agent hermes` → `~/.hermes/skills/memos/`

Or with arguments:

```bash
memos init --api-key YOUR_API_KEY --agent codex
```

### 2. Add Memory

```bash
memos add "User likes Python programming"
```

### 3. Search Memories

```bash
memos search "programming languages"
```

### 4. Chat with MemOS

```bash
memos chat "What do you know about my preferences?"
```

### 5. Get Memories

```bash
memos get user_123
```

### 6. Delete Memory

```bash
memos delete mem_123456
```

### 7. Get Memory Origin

```bash
memos origin mem_123456
```

## Command Reference

### `memos add`

Write a memory into MemOS using simple text input.

Example:

```bash
memos add "User likes Python programming"
```

Parameters:

- `[MESSAGE]`: Memory content to add; required; use `[MESSAGE]` or `--message`.
- `-m, --message`: Memory content to add; optional; alias of `[MESSAGE]`; no separate default.
- `--user-id`: User scope for the memory write; optional; defaults to configured `defaults.user_id`.

### `memos search`

Search memories with semantic retrieval and optional preference/tool/skill expansion.

Example:

```bash
memos search "programming languages" --user-id user_123 --format table --detail simple
```

Parameters:

- `[QUERY]`: Search query text; required; use `[QUERY]` or `--query`.
- `-q, --query`: Search query text; optional; alias of `[QUERY]`; no separate default.
- `--user-id`: User scope for retrieval; optional; defaults to configured `defaults.user_id`.
- `--memory-limit-number`: Main memory recall count; optional; defaults to `9`.
- `--include-preference`: Whether to include preference memory; optional; accepts `true` or `false`; defaults to `true` when omitted.
- `--preference-limit-number`: Preference memory recall count; optional; defaults to `9`.
- `--include-tool-memory`: Whether to include tool memory; optional; accepts `true` or `false`; defaults to `false` when omitted.
- `--tool-memory-limit-number`: Tool memory recall count; optional; defaults to `6`.
- `--include-skill-memory`: Whether to include skill memory; optional; accepts `true` or `false`; defaults to `false` when omitted.
- `--skill-memory-limit-number`: Skill memory recall count; optional; defaults to `6`.
- `--relativity`: Retrieval threshold; not exposed in the current CLI; API default is `0.45`.
- `--format`: Output format; optional; defaults to `agent`.
- `--detail`: Output detail level for non-JSON formats; optional; defaults to `simple`; supported values: `simple`, `detail`.

### `memos get`

Call the documented `get_memory` API to retrieve memories for a user.

Example:

```bash
memos get user_123 --format json --detail detail
```

Parameters:

- `[USER_ID]`: Retrieval scope; effectively required, but if omitted the CLI falls back to configured `defaults.user_id`.
- `--user-id`: Alias of `[USER_ID]`; optional; same fallback as `[USER_ID]`.
- `--page`: Page number; optional; API default is `1` when omitted.
- `--size`: Number of items returned per memory category on the current page; optional; API default is `10` when omitted.
- `--include-preference`: Whether to include preference memory; optional; accepts `true` or `false`; defaults to `true` when omitted.
- `--include-tool-memory`: Whether to include tool memory; optional; accepts `true` or `false`; current CLI exposes this flag, but the official `get_memory` docs do not state the API default when omitted.
- `--format`: Output format; optional; defaults to `agent`.
- `--detail`: Output detail level for non-JSON formats; optional; defaults to `simple`; supported values: `simple`, `detail`.

### `memos delete`

Delete one memory, or delete all memories for a user, using the documented delete API.

Example:

```bash
memos delete mem_123456 --format json
memos delete --user-id user_123 --format json
```

Parameters:

- `MEMORY_ID`: Memory ID to delete; conditionally required; use `MEMORY_ID` to delete one memory.
- `--user-id`: Delete all memories for the given user ID; conditionally required; use `--user-id` to delete all memories for a user.

### `memos origin`

Get the original source payload for a specific memory by memory ID.

Example:

```bash
memos origin mem_123456
memos origin mem_123456 --detail simple
memos origin mem_123456 --detail detail
memos origin mem_123456 --format markdown --detail detail
memos origin mem_123456 --format json
```

Parameters:

- `[MEMORY_ID]`: Memory ID; required.
- `--format`: Output format; optional; defaults to `agent`.
- `--detail`: Output detail level; optional; defaults to `simple`; supported values: `simple`, `detail`.

Default display includes:

- `simple`: `memory_id`, `memory` summary, and source content.
- `detail`: `memory_id`, `memory` summary, source type, role, time, language, and source content.
- source messages are extracted from `data.metadata.sources`.

### `memos extract`

Preview memory candidates from messages without storing them.

Example:

```bash
memos extract "User likes coffee and prefers dark mode" --format json
```

Parameters:

- `[MESSAGE]`: Message content to extract from; required; use `[MESSAGE]` or `--message`.
- `-m, --message`: Message content to extract from; optional; alias of `[MESSAGE]`; no separate default.
- `--user-id`: User scope; optional; defaults to configured `defaults.user_id`.

### `memos rerank`

Rerank candidate documents for a query.

Example:

```bash
memos rerank "python backend" "Flask guide" "React guide" --format json
```

Parameters:

- `[QUERY]`: Query used for reranking; required; use `[QUERY]` or `--query`.
- `[DOCUMENTS]...`: Candidate documents; required; provide one or more documents as positional arguments, repeated `--documents`, or stdin.
- `-q, --query`: Query used for reranking; optional; alias of `[QUERY]`; no separate default.
- `--documents`: Candidate document, repeatable; optional; repeatable alternative to positional `[DOCUMENTS]...`.
- `--top-n`: Return only the top N results; optional; no CLI default; omitted from the request unless provided.
- `--format`: Output format; optional; defaults to `agent`.

### `memos feedback`

Submit feedback content to MemOS.

Example:

```bash
memos feedback "Prefer concise technical answers." --user-id user_123 --format json
```

Parameters:

- `[FEEDBACK_TEXT]`: Feedback content to submit; required; use `[FEEDBACK_TEXT]` or `--feedback-content`.
- `--feedback-content`: Feedback content to submit; optional; alias of `[FEEDBACK_TEXT]`; no separate default.
- `--user-id`: User scope; optional; defaults to configured `defaults.user_id`.

### `memos chat`

Ask MemOS for a memory-informed answer using the documented chat request fields.

Example:

```bash
memos chat "What do you know about my preferences?" --user-id user_123 --format agent
```

Parameters:

- `[QUERY]`: Chat query text; required; use `[QUERY]` or `--query`.
- `-q, --query`: Chat query text; optional; alias of `[QUERY]`; no separate default.
- `--user-id`: User scope; optional; defaults to configured `defaults.user_id`.

## Output Modes

Each subcommand supports trailing `--format`. Only `search` and `get` also support trailing `--detail`:

```bash
memos search "python" --format table --detail simple
memos search "python" --format markdown --detail detail
memos search "python" --format agent --detail simple
memos search "python" --format json --detail detail
memos get user_123 --format json --detail detail
memos add "User prefers TypeScript" --format json
```

## Global Options

- `--api-key KEY`: Override API key from config
- `--base-url URL`: Override API base URL from config
- `--version`: Show version

## Configuration

View current config:

```bash
memos config show
```

Example output includes:
- `API Key`
- `Base URL`
- `Source`
- `Framework`
- default `User ID` and `Conversation ID`

Get/Set specific values:

```bash
memos config get platform.api_key
memos config set defaults.user_id user123
```

## Environment Variables

- `MEMOS_API_KEY`: Your API key
- `MEMOS_BASE_URL`: API base URL (default: https://memos.memtensor.cn/api/openmem/v1)
- `MEMOS_FRAMEWORK`: Override framework attribution (for example `codex`)

## Agent Integration

Use the provided skill to enable memory operations in your agent framework.

Use this skill when:
- you need memory operations such as `extract`, `add`, `search`, `chat`, `get`, and `delete`: `skills/memos-memory/SKILL.md`

Recommended entry point:
1. Start with `skills/memos-memory/SKILL.md`.

## Telemetry & Source Tracking

All CLI requests include:
- `source=cli-<framework>` header when the framework can be identified, for example `source=cli-codex`
- Framework detection (OpenClaw, Hermes, etc.)

Memory API requests also attach framework metadata when it can be detected from
environment variables or the parent process.

This enables usage analytics and framework-specific optimizations.

Framework detection is resolved in this order:
- runtime override
- saved config value from `memos init --agent ...`
- `MEMOS_FRAMEWORK`
- shell / parent-process inference

## Development

### Run from source

```bash
python -m memos_cli --help
```

### Add new commands

1. Create command file in `src/memos_cli/commands/`
2. Register in `src/memos_cli/main.py`
3. Add to appropriate help panel

## License

[Apache 2.0 License.](https://github.com/lijicode/MemOS/blob/main/LICENSE)
