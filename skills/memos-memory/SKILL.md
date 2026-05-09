---
name: memos-memory
version: 1.0.0
description: "MemOS 记忆领域能力：抽取、新增、检索、列出、聊天、读取、删除记忆。用于 P0/P1 记忆主链路。"
metadata:
  requires:
    bins: ["memos"]
  cliHelp: "memos --help"
---

# memos-memory

**CRITICAL — 开始前必须先读取 [`../memos-shared/SKILL.md`](../memos-shared/SKILL.md)**，其中包含初始化、认证、JSON 输出和身份传递规则。

## Commands

- [`+add`](./references/memos-add.md) — Add a memory
- [`+extract`](./references/memos-extract.md) — Extract memory candidates without storing
- [`+search`](./references/memos-search.md) — Search memories
- [`+list`](./references/memos-list.md) — List memories
- [`+chat`](./references/memos-chat.md) — Chat with MemOS
- [`+get`](./references/memos-get.md) — Get a memory by ID
- [`+delete`](./references/memos-delete.md) — Delete a memory by ID

## 使用原则

- 如果用户明确提供了一条新事实、偏好、背景信息，优先考虑 `+add`。
- 如果用户要求“先提取看看会记住什么”，优先考虑 `+extract`。
- 如果用户的问题可能依赖历史上下文，回答前优先考虑 `+search`。
- 如果用户要浏览已有记忆而不是搜索，使用 `+list`。
- 如果已经有具体 `memory_id`，使用 `+get` 或 `+delete`，不要先搜索再猜。
- 搜索词不要机械照抄整段对话，优先提炼关键词、偏好、实体名和意图。

## 常见工作流

### 1. 首次验证链路

```bash
memos add -m "User likes Python"
memos search -q "Python"
```

### 2. Agent 检索

```bash
memos search --json -q "user preferences about restaurants" --user-id <USER_ID> --conversation-id <CONV_ID>
```

### 3. Agent 抽取预览

```bash
memos extract --json -m "User likes coffee and prefers dark mode" --user-id <USER_ID> --conversation-id <CONV_ID>
```

### 4. Agent 存储

```bash
memos add --json -m "User is allergic to peanuts" --user-id <USER_ID> --conversation-id <CONV_ID>
```

### 5. 定位并删除

```bash
memos get --json <MEMORY_ID>
memos delete --json <MEMORY_ID>
```

## 输出要求

- 文本模式适合人类终端阅读。
- 只要后续步骤需要解析 `memory_id`，就使用 `--json`。
- 列表型结果优先从 `data` 中读取数组，从 `count` 读取结果数量。
