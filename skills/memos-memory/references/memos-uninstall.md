# `memos uninstall`

Use this command when the user asks to uninstall, disable, remove, or stop using MemOS in the current agent.

Do not run `memos search` or `memos add` in the same turn. Uninstall intent is an administrative action, not a memory workflow.

## Command

```bash
memos uninstall --agent <CURRENT_AGENT> --yes
```

## Arguments

- `--agent <CURRENT_AGENT>` (required): current agent name, such as `codex`, `cursor`, `claude`, `openclaw`, or `hermes`.
- `--yes` / `-y`: skip confirmation for agent workflows.
- `--remove-config`: also remove `~/.memos/config.yaml` when the user explicitly wants local configuration removed.

## Behavior

- removes the bundled MemOS skill from the target agent skills directory;
- removes only the managed MemOS guidance block from agent guidance files such as `AGENTS.md` or `CLAUDE.md`;
- keeps guidance files in place even when they become empty after MemOS content is removed;
- clears MemOS-managed standalone guidance content for agents that use standalone rule files, while keeping the file itself;
- does not remove the npm package or global `memos` binary.

To remove the global CLI package too, tell the user to run:

```bash
npm uninstall -g @memtensor/memos-cloud-cli
```
