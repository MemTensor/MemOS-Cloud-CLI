# Config Domain Skeleton

Use this domain when:
- you are generating a configuration-oriented MemOS skill;
- you need to describe initialization, config inspection, and config updates;
- the skill must explain how runtime overrides interact with persisted config.

Never do:
- print raw API keys in docs, logs, or agent output examples;
- modify config blindly without showing how to inspect current state;
- assume default user or conversation config is harmless in all workflows.

Core concepts:
- `init`: first-time setup of API key and base URL.
- `config`: persisted CLI configuration for platform and default identities.
- runtime override: use `--api-key` and `--base-url` to override local config for one command.

Resource relationships:

```
MemOS CLI
├── init
└── config
    ├── show
    ├── get
    └── set
```

Intent to command mapping:

- initialize a fresh CLI environment: `memos init`
- inspect current config: `memos config show`
- read one config key: `memos config get <key>`
- update one config key: `memos config set <key> <value>`

Working rules:
- check `memos config show` before changing values during debugging;
- call out that `defaults.user_id` and `defaults.conversation_id` may affect later behavior;
- use explicit runtime overrides only when you need to bypass local config.

Example commands:

```bash
memos init --api-key <API_KEY> --base-url https://memos.memtensor.cn/api/openmem/v1
memos config show
memos config get platform.base_url
memos config set <key> <value>
```
