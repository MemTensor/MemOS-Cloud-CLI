# MemOS CLI

面向 AI Agent 的通用记忆命令行接口。

## 项目结构

```text
MemOS-CLI/
├── src/memos_cli/
│   ├── __init__.py          # 包版本
│   ├── __main__.py          # python -m memos_cli 入口
│   ├── main.py              # 主 CLI 应用（Typer）
│   ├── config.py            # 配置管理
│   ├── output.py            # 输出格式化（text/json）
│   ├── branding.py          # 品牌色和彩色符号
│   ├── state.py             # 运行时状态管理（agent mode）
│   ├── telemetry.py         # 调用归因与遥测
│   ├── backend/             # API 后端层
│   │   ├── base.py          # 抽象基类
│   │   └── memos_api.py     # MemOS Cloud API 实现
│   └── commands/            # CLI 命令
│       ├── init.py          # memos init
│       ├── config_cmd.py    # memos config (show/get/set)
│       └── memory.py        # add/search/get/delete/extract/rerank/feedback/chat
├── skills/
│   ├── memos-memory/        # 记忆领域 skill（P0 命令）
│   │   ├── SKILL.md         # Skill 入口与使用规范
│   │   └── references/      # Skill 参考文档
│   │       ├── memos-add.md
│   │       ├── memos-chat.md
│   │       ├── memos-delete.md
│   │       ├── memos-extract.md
│   │       ├── memos-get.md
│   │       └── memos-search.md
├── pyproject.toml
└── README.md
```

## 安装

```bash
pip install -e .
```

## 快速开始

### 1. 初始化

```bash
memos init --agent codex
```

该命令会同时安装 MemOS 记忆操作 skill 到你显式指定的 Agent skills 目录。
`--agent` 为必填项，不支持安装到通用全局目录。
当 shell 能被识别时，该命令也会自动安装命令补全。

支持的目标：
- `--agent codex` → `~/.codex/skills/memos/`
- `--agent cursor` → `~/.cursor/skills/memos/`
- `--agent claude` → `~/.claude/skills/memos/`
- `--agent openclaw` → `~/.openclaw/skills/memos/`
- `--agent hermes` → `~/.hermes/skills/memos/`

也可以直接带参数：

```bash
memos init --api-key YOUR_API_KEY --agent codex
```

### 2. 新增记忆

```bash
memos add "用户喜欢 Python 编程"
```

### 3. 搜索记忆

```bash
memos search "编程语言偏好"
```

### 4. 结合记忆对话

```bash
memos chat "你知道我的偏好吗？"
```

### 5. 获取记忆

```bash
memos get user_123
```

### 6. 删除记忆

```bash
memos delete mem_123456
```

## 命令说明

### `memos add`

用于向 MemOS 写入一条记忆内容。

示例：

```bash
memos add "用户喜欢 Python 编程"
```

参数说明：

- `[MESSAGE]`：要写入的记忆内容；必填；`[MESSAGE]` 与 `--message` 二选一。
- `-m, --message`：要写入的记忆内容；可选；`[MESSAGE]` 的别名；无单独默认值。
- `--user-id`：用户维度；可选；默认取配置中的 `defaults.user_id`。

### `memos search`

用于搜索记忆。

示例：

```bash
memos search "编程语言偏好" --user-id user_123 --format table --detail simple
```

参数说明：

- `[QUERY]`：搜索关键词；必填；`[QUERY]` 与 `--query` 二选一。
- `-q, --query`：搜索关键词；可选；`[QUERY]` 的别名；无单独默认值。
- `--user-id`：用户维度；可选；默认取配置中的 `defaults.user_id`。
- `--memory-limit-number`：主记忆召回条数；可选；默认值为 `9`。
- `--include-preference`：是否召回偏好记忆；可选；接受 `true` 或 `false`；不传时默认 `true`。
- `--preference-limit-number`：偏好记忆召回条数；可选；默认值为 `9`。
- `--include-tool-memory`：是否召回工具记忆；可选；接受 `true` 或 `false`；不传时默认 `false`。
- `--tool-memory-limit-number`：工具记忆召回条数；可选；默认值为 `6`。
- `--include-skill-memory`：是否召回技能记忆；可选；接受 `true` 或 `false`；不传时默认 `false`。
- `--skill-memory-limit-number`：技能记忆召回条数；可选；默认值为 `6`。
- `--relativity`：召回阈值；当前 CLI 未暴露；接口默认值为 `0.45`。
- `--format`：输出格式；可选；默认值为 `table`。
- `--detail`：非 JSON 输出的详略级别；可选；默认值为 `simple`；支持 `simple`、`detail`。

### `memos get`

用于调用官网 `get_memory` 接口，按用户获取记忆。

示例：

```bash
memos get user_123 --format json --detail detail
```

参数说明：

- `[USER_ID]`：用户维度；实际上必填，但若不传 CLI 会回退到配置中的 `defaults.user_id`。
- `--user-id`：`[USER_ID]` 的兼容别名；可选；与 `[USER_ID]` 使用同样的回退规则。
- `--page`：页码；可选；不传时接口默认值为 `1`。
- `--size`：指定每一类记忆在当前页返回的条目数量；可选；不传时接口默认值为 `10`。
- `--include-preference`：是否召回偏好记忆；可选；接受 `true` 或 `false`；不传时默认 `true`。
- `--include-tool-memory`：是否召回工具记忆；可选；接受 `true` 或 `false`；当前 CLI 已暴露该参数，但官方 `get_memory` 文档未说明不传时的接口默认值。
- `--format`：输出格式；可选；默认值为 `table`。
- `--detail`：非 JSON 输出的详略级别；可选；默认值为 `simple`；支持 `simple`、`detail`。

### `memos delete`

用于删除一条记忆，或删除某个用户的全部记忆。

示例：

```bash
memos delete mem_123456 --format json
memos delete --user-id user_123 --format json
```

参数说明：

- `MEMORY_ID`：待删除的记忆 ID；条件必填；传 `MEMORY_ID` 表示删除单条记忆。
- `--user-id`：删除该用户的全部记忆；条件必填；传 `--user-id` 表示删除该用户的全部记忆。

### `memos extract`

用于从消息中提取候选记忆，但不写入。

示例：

```bash
memos extract "用户喜欢咖啡，也偏好深色模式" --format json
```

参数说明：

- `[MESSAGE]`：待提取的消息内容；必填；`[MESSAGE]` 与 `--message` 二选一。
- `-m, --message`：待提取的消息内容；可选；`[MESSAGE]` 的别名；无单独默认值。
- `--user-id`：用户维度；可选；默认取配置中的 `defaults.user_id`。

### `memos rerank`

用于对候选文档做重排。

示例：

```bash
memos rerank "python 后端" "Flask guide" "React guide" --format json
```

参数说明：

- `[QUERY]`：重排查询；必填；`[QUERY]` 与 `--query` 二选一。
- `[DOCUMENTS]...`：候选文档文本；必填；可通过位置参数、`--documents`提供多个候选文档。
- `-q, --query`：重排查询；可选；`[QUERY]` 的别名；无单独默认值。
- `--documents`：候选文档文本；可选；可重复传入。
- `--top-n`：只返回前 N 条；可选；CLI 不设置默认值；不传则请求体不带该字段。
- `--format`：输出格式；可选；默认值为 `table`。

### `memos feedback`

用于提交反馈内容。

示例：

```bash
memos feedback "偏好简洁、直接的技术回答。" --user-id user_123 --format json
```

参数说明：

- `[FEEDBACK_TEXT]`：反馈内容；必填；`[FEEDBACK_TEXT]` 与 `--feedback-content` 二选一。
- `--feedback-content`：反馈内容；可选；`[FEEDBACK_TEXT]` 的别名；无单独默认值。
- `--user-id`：用户维度；可选；默认取配置中的 `defaults.user_id`。

### `memos chat`

用于基于 MemOS 记忆进行问答。

示例：

```bash
memos chat "你知道我的偏好吗？" --user-id user_123 --format agent
```

参数说明：

- `[QUERY]`：对话问题；必填；`[QUERY]` 与 `--query` 二选一。
- `-q, --query`：对话问题；可选；`[QUERY]` 的别名；无单独默认值。
- `--user-id`：用户维度；可选；默认取配置中的 `defaults.user_id`。


## 输出模式

所有子命令都支持在命令末尾追加 `--format`。只有 `search`、`get` 额外支持在命令末尾追加 `--detail`：

```bash
memos search "python" --format table --detail simple
memos search "python" --format markdown --detail detail
memos search "python" --format agent --detail simple
memos search "python" --format json --detail detail
memos get user_123 --format json --detail detail
memos add "用户偏好 TypeScript" --format json
```

## 全局选项

- `--api-key KEY`：覆盖本地配置中的 API Key
- `--base-url URL`：覆盖 API Base URL
- `--version`：显示版本号

## 配置

查看当前配置：

```bash
memos config show
```

输出中会包含：
- `API Key`
- `Base URL`
- `Source`
- `Framework`
- 默认 `User ID` 与 `Conversation ID`

获取 / 设置单个配置项：

```bash
memos config get platform.api_key
memos config set defaults.user_id user123
```

## 环境变量

- `MEMOS_API_KEY`：你的 API Key
- `MEMOS_BASE_URL`：API Base URL，默认值为 `https://memos.memtensor.cn/api/openmem/v1`
- `MEMOS_FRAMEWORK`：覆盖 framework 归因，例如 `codex`

## Agent 集成

你可以使用仓库提供的 skill，把 MemOS 的长期记忆能力接入你的 Agent 框架。

适用场景：
- 需要记忆操作，如 `extract`、`add`、`search`、`chat`、`get`、`delete`：`skills/memos-memory/SKILL.md`

推荐入口：
1. 直接从 `skills/memos-memory/SKILL.md` 开始

## 调用归因与来源标记

所有 CLI 请求都会附带：
- 可识别框架时附带 `source=cli-<framework>` 标记，例如 `source=cli-codex`
- 框架识别信息（如 OpenClaw、Hermes 等）

当框架可从环境变量或父进程识别时，记忆 API 请求也会附带对应的 framework 信息。

这有助于做使用统计、来源区分和框架级优化。

framework 的识别顺序为：
- 运行时覆盖值
- `memos init --agent ...` 保存的配置值
- `MEMOS_FRAMEWORK`
- shell / 父进程推断

## 开发

### 从源码运行

```bash
python -m memos_cli --help
```

### 添加新命令

1. 在 `src/memos_cli/commands/` 下创建命令文件
2. 在 `src/memos_cli/main.py` 中注册
3. 添加到合适的 help panel

## License
[Apache 2.0 License.](https://github.com/lijicode/MemOS/blob/main/LICENSE)
