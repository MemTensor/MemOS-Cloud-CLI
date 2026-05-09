---
name: memos-shared
version: 1.0.0
description: "MemOS CLI 通用能力：初始化、配置、认证、JSON 输出约定、用户与会话标识传递规则。当 Agent 需要先确认 MemOS CLI 是否可用、如何初始化、如何选择输出模式、如何传 user/session/framework 上下文时使用。"
metadata:
  requires:
    bins: ["memos"]
  cliHelp: "memos --help"
---

# memos-shared

这个 Skill 只包含 MemOS CLI 的通用规则。调用具体记忆能力前，先遵守这些约定。

## 初始化

首次使用前先确保 CLI 已完成初始化：

```bash
memos init
```

也可以显式传参：

```bash
memos init --api-key <API_KEY> --base-url https://memos.memtensor.cn/api/openmem/v1
```

初始化成功后可用以下命令检查配置：

```bash
memos config show
memos config get platform.base_url
```

## 全局约定

- 面向 Agent 的调用优先使用 `--json`。
- 当用户或框架提供了稳定身份时，优先传 `--user-id`。
- 当用户或框架提供了稳定会话时，优先传 `--conversation-id`。
- 多 Agent 场景优先传 `--agent-id`；应用级隔离可传 `--app-id`；单次运行链路可传 `--run-id`。
- 需要覆盖本地配置时，可以在任何命令上追加：
  - `--api-key`
  - `--base-url`

## 身份与来源归因

MemOS CLI 会自动附带：

- `X-Source: cli`
- 可检测到时附带 `X-Framework`

如果自动检测不到框架，可以显式设置环境变量：

```bash
export MEMOS_FRAMEWORK=openclaw
```

## 输出约定

默认输出是适合人类阅读的文本。

Agent 模式使用：

```bash
memos <command> --json ...
```

JSON 响应使用统一 envelope：

- `status`
- `command`
- `duration_ms`（部分命令）
- `scope`
- `count`（列表型命令）
- `data`

## 错误处理

- `Authentication failed`：通常表示 API Key 无效或过期。
- `API error`：通常表示路由、参数或服务端响应异常。
- 命令缺少必要输入时会直接退出并返回非 0 状态码。

## 下一步

按任务继续读取：

- [`../memos-config/SKILL.md`](../memos-config/SKILL.md)
- [`../memos-memory/SKILL.md`](../memos-memory/SKILL.md)
- [`../memos-kb/SKILL.md`](../memos-kb/SKILL.md)
- 自动化工作流：[`../memos-memory-agent/SKILL.md`](../memos-memory-agent/SKILL.md)
