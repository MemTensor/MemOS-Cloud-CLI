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
│       ├── kb.py            # kb create / file add
│       └── memory.py        # add/search/list/chat/get/delete
├── skills/
│   ├── memos-shared/        # Shared config and runtime rules
│   ├── memos-config/        # Config and initialization skill
│   ├── memos-memory/        # Memory domain skill (P0 commands)
│   ├── memos-kb/            # Knowledge base domain skill
│   ├── memos-memory-agent/  # Automated recall/capture workflow
│   └── memory_skill.md      # Backward-compatible pointer
├── pyproject.toml
└── README.md
```

## Installation

```bash
pip install -e .
```

## Quick Start

### 1. Initialize

```bash
memos init
```

Or with arguments:

```bash
memos init --api-key YOUR_API_KEY --base-url https://memos.memtensor.cn/api/openmem/v1
```

### 2. Add Memory

```bash
memos add -m "User likes Python programming"
```

### 3. Search Memories

```bash
memos search -q "programming languages"
```

### 4. List Memories

```bash
memos list
```

### 5. Chat with MemOS

```bash
memos chat "What do you know about my preferences?"
```

### 6. Get Memory by ID

```bash
memos get mem_123456
```

### 7. Delete Memory

```bash
memos delete mem_123456
```

### 8. Create Knowledge Base

```bash
memos kb create "Project Docs" --description "Internal knowledge base"
```

### 9. Add Documents to a Knowledge Base

```bash
memos kb file add kb_123 https://example.com/doc-a.pdf https://example.com/doc-b.pdf
```

## Output Modes

Each subcommand supports `--format` and `--detail` at the end of the command line:

```bash
memos search -q "python" --format table --detail simple
memos search -q "python" --format markdown --detail detail
memos search -q "python" --format agent --detail simple
memos search -q "python" --format json --detail detail
memos add -m "User prefers TypeScript" --format json
```

## Global Options

- `--api-key KEY`: Override API key from config
- `--base-url URL`: Override base URL from config
- `--version`: Show version

## Configuration

View current config:

```bash
memos config show
```

Get/Set specific values:

```bash
memos config get platform.api_key
memos config set defaults.user_id user123
```

## Environment Variables

- `MEMOS_API_KEY`: Your API key
- `MEMOS_BASE_URL`: API base URL (default: https://memos.memtensor.cn/api/openmem/v1)

## Agent Integration

Use the provided skills to enable automatic memory management in your agent framework.

Use these skills when:
- you need shared setup, identity, and per-command output conventions such as trailing `--format` and `--detail`: `skills/memos-shared/SKILL.md`
- you need configuration and initialization commands: `skills/memos-config/SKILL.md`
- you need memory operations such as `extract`, `add`, `search`, `list`, `chat`, `get`, and `delete`: `skills/memos-memory/SKILL.md`
- you need knowledge base operations: `skills/memos-kb/SKILL.md`
- you need the default agent workflow for retrieve-before-respond and store-after-respond: `skills/memos-memory-agent/SKILL.md`

Recommended entry points:
1. Start with `skills/memos-memory-agent/SKILL.md` for automated agent workflows.
2. Start with `skills/memos-shared/SKILL.md` if setup or runtime conventions come first.

## Telemetry & Source Tracking

All CLI requests include:
- `source=cli` header
- Framework detection (OpenClaw, Hermes, etc.)

Memory API requests also attach framework metadata when it can be detected from
environment variables or the parent process.

This enables usage analytics and framework-specific optimizations.

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

MIT
