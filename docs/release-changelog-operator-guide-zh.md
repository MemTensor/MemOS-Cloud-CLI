# MemOS Cloud CLI 更新日志自动化使用说明

更新时间：2026-07-28

本文面向 CLI 发布人员、Doc Agent 维护人员和文档审核人员，说明
`MemTensor/MemOS-Cloud-CLI` 如何把一次正常的 GitHub Release 转换为官网
Plugin tab 的中英文更新日志。

这次改造只解决“从 CLI Release 提取和发布更新日志”。它不增加四平台构建、
SHA-256 manifest、npm 发布或 OSS 上传，也不会替 CLI 负责人决定下一个版本。

---

## 1. 先看结论

完整链路是：

```text
CLI 负责人确定 <next-version> 并完成真实代码、版本号更新
-> Actions 手动运行 dry_run=true
-> 审核 GitHub Release Notes 和中英文 Plugin changelog 预览
-> Actions 手动运行 dry_run=false，并输入精确确认词
-> 在 main 当前提交创建 v<next-version> Tag
-> 沿用仓库现有 Linux/Windows 构建并创建 Draft GitHub Release
-> CLI 负责人审核 Draft 的 Tag、What's Changed 和资产
-> 人工点击 Publish
-> GitHub 发送 release.published webhook
-> Doc Agent 按相邻 Tag 收集整个 CLI 仓库的变更
-> 生成 3 组候选，自动选择、校验，必要时最多修复 3 轮
-> 创建 MemOS-Docs Draft PR
-> 文档 PR 审核、合并
-> 发布 pre
-> 等待 360 秒
-> 发布 gray
-> CLI 模块程序员检查灰度内容
-> 人工确认后才允许 production
```

GitHub Actions 仍然存在，而且承担版本输入校验、dry-run、现有二平台构建、
Tag 和 Draft Release 创建。Doc Agent 不替代 Actions；它从
`release.published` 开始接管官网文案链路。

---

## 2. GitHub Release 里分别是谁写什么

有两份不同用途的文案：

1. **GitHub Release body**
   - 由 GitHub Generate Release Notes API 根据本次 Tag 和上一个 Tag 生成。
   - 内容定位是工程侧的 `What's Changed`。
   - dry-run artifact 里的 `github-release-notes.md` 就是发布前预览。
   - 发布人员在 Draft Release 阶段进行最后人工检查。

2. **官网 Plugin tab 更新日志**
   - 由 Doc Agent 根据同一段 Git Tag range 的真实 Git 证据生成。
   - 同时生成中文和英文。
   - 先生成 3 组候选，再做确定性选择、来源覆盖校验和最多 3 轮修复。
   - 最终通过 MemOS-Docs Draft PR 进入 pre、gray 和 production。

不要把 Doc Agent 生成的官网短文案直接复制成 GitHub Release body，也不要把
GitHub 自动生成的全部 commit 列表原样放进 Plugin tab。

---

## 3. 当前真实状态

截至 2026-07-28 的只读审核结果：

- 正式仓库 `main` 的三个版本源均为 `1.0.6`。
- npm 最新正式版本为 `1.0.6`。
- 正式仓库还没有远程 Git Tag。
- 正式仓库还没有 GitHub Release。
- 本自动化没有选择或创造任何 `<next-version>`。
- Release webhook 已启用 Release 事件；创建时的 ping 返回成功。当前部署接受
  HTTP 的 106 Doc Agent endpoint。
- Doc Agent 已有 `memos-cloud-cli` 的整仓 mapping 设计。

因此，合并自动化以后也不能立刻随意填写一个新版本。真实 dry-run 必须等待：

- CLI 负责人明确下一个版本；
- 下一个版本的真实代码已进入目标分支；
- 三个版本源都改成同一个 `<next-version>`；
- `v1.0.6` 基线 Tag 经正式仓库维护者批准并补齐。
- webhook 和 Doc Agent Actions endpoint 已配置到可访问的 106 endpoint；当前接受 HTTP。

---

## 4. 一次性补齐 v1.0.6 基线

经过 npm `gitHead`、提交时间、版本文件和 main 可达性联合校验，
`v1.0.6` 的基线提交是：

```text
c18ced54beeb817f6d3f0def1d43eca66da94817
```

这里只允许补一个可信比较起点，不允许补造历史 GitHub Release。建议按下面步骤让
维护者批准并执行：

1. 在本 PR 或单独 Issue 里贴出上面的证据。
2. 请拥有 `MemTensor/MemOS-Cloud-CLI` 写权限的维护者评论确认：
   `APPROVE BACKFILL v1.0.6 c18ced54beeb817f6d3f0def1d43eca66da94817`。
3. 维护者从干净 checkout 执行下面命令。第一个 `git ls-remote` 必须没有输出；
   如果已经有 `v1.0.6`，不要覆盖、不要 force-push，先回到 PR 里确认。

```bash
git clone git@github.com:MemTensor/MemOS-Cloud-CLI.git
cd MemOS-Cloud-CLI
git fetch origin main
git ls-remote --tags origin refs/tags/v1.0.6
git rev-parse --verify c18ced54beeb817f6d3f0def1d43eca66da94817^{commit}
git show --no-patch --format='%H%n%s%n%aI' c18ced54beeb817f6d3f0def1d43eca66da94817
git tag v1.0.6 c18ced54beeb817f6d3f0def1d43eca66da94817
git push origin refs/tags/v1.0.6
git ls-remote --tags origin refs/tags/v1.0.6
```

原因是自动提取需要一个可信的比较
起点；如果没有基线，下一次会把过多历史变化误认为一个版本的更新。

这个 Git Tag 基线与二进制 checksum 无关。本链路不生成 SHA-256 manifest。

---

## 5. 合并前必须通过的检查

PR 和合并到 `main` 的变更都会运行：

```text
MemOS CLI Release — Pre/Post-Merge Checks
```

该检查具有以下特性：

- 仓库权限只有 `contents: read`；
- 不读取 Doc Agent Secret；
- 不调用真实 Release workflow；
- 不创建 Tag、Release、Docs PR 或部署；
- 先用 actionlint 检查 workflow 语法、表达式、Action 参数和 Job 定义；
- 再运行 Node 测试和脚本语法检查；
- 导出 `v99.99.98...v99.99.99` 的合成离线 artifact。

`99.99.x` 只用于证明机制，绝不是下一次正式版本。看到这个 artifact 时，审核者
只检查格式、质量门禁和零副作用，不检查它是不是一份真实 Release 文案。

这一设计也避免了常见的 GitHub Actions 低级错误：只看 YAML 文本没有报错，
但因为表达式、Action 输入、可复用 workflow 权限或调用接口不兼容，运行在
创建 Job 之前就 `startup_failure`。

当前 CLI 检查 workflow 不使用 `workflow_call`，也不会从只读 CI 调用拥有写权限
的 Release workflow。测试会持续禁止这两种链路被意外混合。

---

## 6. 正式仓库需要的 Secret

在正式仓库的 **Settings -> Secrets and variables -> Actions** 中配置：

```text
DOC_AGENT_RELEASE_NOTES_DRAFT_URL
DOC_AGENT_RELEASE_NOTES_DRAFT_TOKEN
DOC_AGENT_RELEASE_FAILURE_URL
```

注意：

- 三个值都必须使用 GitHub Actions encrypted secret。
- 两个 URL 可以使用 HTTP 或 HTTPS；当前 106 部署使用 HTTP。
- `DOC_AGENT_RELEASE_FAILURE_URL` 必须和 `DOC_AGENT_RELEASE_NOTES_DRAFT_URL`
  使用同一个 origin，避免把同一个 Bearer token 发到错误 host。
- 不要写进 workflow、代码、Issue、PR 描述或 artifact。
- 不要在日志里打印 URL 或 Token。
- dry-run 也会调用 Doc Agent 生成候选，因此同样需要前两个 Secret。
- 失败上报只发送经过脱敏、数量受限的失败摘要，不发送完整 Secret。

`github.token` 由 GitHub Actions 自动提供，不需要手工创建 PAT。

GitHub-hosted runner 会把 Bearer Token 和发布证据发送给 Draft endpoint。当前部署
明确接受 HTTP，因此管理员应确认 URL 只写在 GitHub Actions encrypted secrets 中，
不要写进代码、PR、日志或 artifact。GitHub webhook 依靠 HMAC 签名验证来源和完整性；
HTTP 能工作，但传输内容不是加密的。

---

## 7. Doc Agent mapping 必须满足什么

正式配置需要把独立 CLI 仓库映射为：

```yaml
sources:
  - id: memos-cloud-cli
    trigger: github_release
    source_repo: MemTensor/MemOS-Cloud-CLI
    tag_patterns:
      - 'v*'
    product_paths:
      - '**'
    format: memos_docs_plugin_changelog
    renderer_options:
      product_title:
        zh: MemOS CLI
        en: MemOS CLI
    docs:
      repo: MemTensor/MemOS-Docs
      branch: v2
      files:
        zh: content/cn/plugin-changelog.yml
        en: content/en/plugin-changelog.yml
```

这里的 `product_paths: ['**']` 表示“整个独立 CLI 仓库”，不是四平台，也不是
MemOS 主仓中的子目录过滤。

必须写入：

```text
content/cn/plugin-changelog.yml
content/en/plugin-changelog.yml
```

不能写入 Highlight 使用的：

```text
content/cn/changelog.yml
content/en/changelog.yml
```

Doc Agent 的配置和实现还必须部署到实际运行实例。只在某台机器的未提交工作区
修改 mapping，不等于正式链路已经持久化。第一次真实 Release 前需要由 Doc
Agent 维护者确认：配置已纳入其受控版本并部署，服务重启后不会丢失。

---

## 8. 第一次真实 dry-run 怎么操作

这里的“真实”表示使用正式仓库、真实候选版本和真实 Doc Agent，但仍然没有任何
发布副作用。

### 8.1 前置条件

先确认：

- `v1.0.6` 基线 Tag 已由维护者批准并存在于 origin。
- CLI 负责人已经选择 `<next-version>`。
- `package.json`、`pyproject.toml`、`src/memos_cli/__init__.py` 的版本完全一致。
- 目标分支/提交包含准备发布的真实代码。
- 三个 Doc Agent Secret 均已配置。
- Doc Agent 正式 mapping 已部署。
- Doc Agent Actions endpoint 和 Release webhook 都已配置到可访问的 106 endpoint。

### 8.2 Actions 输入

打开 **Actions -> MemOS CLI — Release -> Run workflow**：

```text
Run workflow from: main
version: <next-version>
target_ref: 要检查的分支名或 commit SHA
dry_run: true
create_draft_release: true
recover_existing_release: false
fault_case: none
publish_confirmation: 留空
```

版本输入不带前缀 `v`。例如负责人批准的是 `2.0.0`，填写 `2.0.0`，不要填写
`v2.0.0`。

workflow 的分支选择器必须选受保护的默认分支 `main`。如果要预览尚未合并的
候选分支，把候选分支名写入 `target_ref`；不要切换 workflow 自身的运行分支。
这样实际读取 Secret 和执行检查的脚本始终来自受信任的默认分支。

### 8.3 dry-run 必须检查的 artifact

下载：

```text
memos-cloud-cli-release-inspection
```

至少检查：

- `README.md`
  - `quality_ok: true`
  - `publish_blocked: false`
  - previous/current Tag 正确
  - target SHA 正确
- `github-release-notes.md`
  - 比较范围正确
  - 没有把旧版本历史混入本次
  - 没有 Secret、内网 URL 或无关 CI 噪声
- `evidence.json`
  - `evidence_scope: whole_repository`
  - `product_paths: ["**"]`
  - 用户可感知的重要提交没有遗漏
- `release-notes-draft.json`
  - 有 3 组候选的选择记录
  - 每条官网文案都有真实 `source_refs`
- `docs-preview.md`
  - 中文只出现中文正文
  - 英文只出现英文正文
  - 文案表达具体 CLI 影响，而不是“优化了功能”一类空话
- `quality-report.json`
  - `ok: true`
  - `missing_required_count: 0`
  - 修复轮次不超过上限
- `release-contract.json`
  - dry-run 的所有副作用均为 `false`
  - `direct_publish_allowed: false`

远端还应保持：

- 不存在 `v<next-version>`；
- 不存在对应 GitHub Release；
- 不存在由这次 dry-run 创建的 Docs PR；
- 没有 pre、gray 或 production 部署。

如果上述任何一点不成立，不进入真实发布。

---

## 9. 是否需要跑故障注入

正常 dry-run 通过后，可以在正式发布前额外运行质量门禁故障注入：

```text
mixed_language
missing_source_refs
invalid_source_ref
missing_important_commit
thirteen_items
too_long
```

每次都必须保持：

```text
dry_run: true
```

预期行为是第一轮候选被故意破坏，校验器指出精确问题，Doc Agent 收到修复请求，
后续合法候选通过。如果超过 3 轮仍不合法，流程必须失败关闭。

任何 `dry_run=false` 与非 `none` 的 fault case 组合都会在构建、Tag 和 Release
之前被拒绝。

---

## 10. 真实发布怎么操作

只有 dry-run artifact 审核通过、发布提交已经在受保护的默认分支 `main` 后，
才能运行：

```text
version: <next-version>
target_ref: main
dry_run: false
create_draft_release: true
recover_existing_release: false
fault_case: none
publish_confirmation: PUBLISH v<next-version>
```

确认词必须逐字符匹配。例如版本是 `2.0.0`：

```text
PUBLISH v2.0.0
```

workflow 会：

1. 再次检查三个版本源。
2. 检查运行来源和目标 SHA 都是当前默认分支。
3. 查找相邻的上一个 SemVer Tag。
4. 生成并校验 Release/官网文案。
5. 构建仓库原本支持的 Linux x64 和 Windows x64 资产。
6. 创建或更新 Draft 前重新读取远端 `refs/heads/main`；如果 main 在构建期间前进，
   流程会失败并要求重新 dry-run。
7. 在目标 SHA 创建 `v<next-version>` Tag。
8. 创建 Draft GitHub Release。

它不会自动 Publish。发布人员必须打开 Draft，人工检查：

- Tag 是否指向正确 main commit；
- 标题是否正确；
- `What's Changed` 是否只覆盖预期 Tag range；
- Linux/Windows 资产是否齐全；
- 没有内部信息或明显错误。

检查完成后人工点击 **Publish release**。此操作才会触发正式
`release.published` webhook。

如果发布的是 SemVer prerelease，workflow 会把 GitHub Release 标成
prerelease；当前正式 Docs mapping 会忽略 prerelease，不应期待它自动创建正式
官网更新日志。

---

## 11. Tag 已创建但 Release 失败时怎么办

正常重跑不会自动把一个旧 Tag 包装成新 Release。

如果确认：

- Tag 指向本次预期的目标 SHA；
- GitHub 上确实不存在对应 Release；
- 这是同一次失败运行的恢复；

才使用：

```text
recover_existing_release: true
```

如果 Tag 指向错误提交，流程会失败关闭，不会移动 Tag。此时不要自行删除或强推
Tag，应由正式仓库维护者先审计并决定恢复方式。

如果 Draft Release 已存在，重跑会校验 Draft/prerelease 状态，更新文案并安全地
补齐资产。若 Release 已经发布，流程保持其不变。

---

## 12. Webhook 后应该看到什么

人工发布正式、非 prerelease Release 后：

1. GitHub Webhook 页面出现 `release` delivery。
2. delivery 的 action 为 `published`。
3. Doc Agent 返回已识别 `memos-cloud-cli`。
4. previous/current Tag 与本次发布一致。
5. evidence 范围是整个 CLI 仓库。
6. 三候选选择和来源覆盖校验通过。
7. 创建一个 MemOS-Docs Draft PR。
8. PR 只修改中英文 `plugin-changelog.yml`。

以下任一情况都应阻止 Docs PR：

- 找不到上一个 Tag；
- 任何候选请求缺失，无法完成本地选择；
- `source_refs` 不属于真实 Tag range；
- 用户可感知的重要提交没有覆盖；
- 只有 CI、测试或文档变更，却生成了面向用户的更新条目；
- 中文、英文混写；
- 文案包含内部 URL 或凭据特征；
- 文案只有空泛的“新增/修复/优化”；
- 条目超过 12 条或单条过长；
- 3 轮修复仍然失败。

重复投递同一个 Release 必须幂等：已有同版本内容时，不得重复追加。

---

## 13. 文档 PR、pre、gray 和 production

MemOS-Docs Draft PR 创建后：

1. 核对中英文版本、分类、条目数量和产品名称 `MemOS CLI`。
2. 核对每条文案能回溯到 evidence 中的 commit/PR。
3. 确认没有改动 Highlight changelog 或无关文件。
4. 通过检查后合并 PR。
5. 发布 pre。
6. 等待 360 秒。
7. 发布 gray。
8. 由对应 CLI 模块程序员在灰度页面逐条检查。
9. 只有人工确认通过后才发布 production。

自动化不会代替第 8、9 步。

如果灰度内容有误，修正 MemOS-Docs Draft PR 或补一个纠正文档 PR，重新走 pre
和 gray；在修复确认前保持 production 阻塞。

---

## 14. 常见低级错误和处理方式

### 14.1 Actions 一启动就失败，没有 Job 日志

优先检查：

- workflow YAML 或 `${{ }}` 表达式是否合法；
- Action 的输入名是否存在；
- 是否把有写权限/Secret 的 release workflow 错当成只读 reusable workflow；
- caller 与 `workflow_call` 的 permissions/secrets 是否兼容。

本实现会在 PR 上先运行 actionlint，并禁止只读检查 workflow 调用正式 Release
workflow。不要为了复用几行步骤而重新把两者耦合。

### 14.2 dry-run 提示找不到上一个 Tag

确认维护者是否已批准并补齐 `v1.0.6` 基线。不要绕过门禁，也不要让脚本退化为
“从仓库第一条提交开始比较”。

### 14.3 版本文件不一致

同时检查：

```text
package.json
pyproject.toml
src/memos_cli/__init__.py
```

三处必须与 Actions 的 `version` 输入完全一致。

### 14.4 dry-run 意外生成 Tag 或 Release

这是阻断级问题。立即停止真实发布，保存 run URL 和 artifact，确认实际输入
`dry_run=true`，并检查 `release-contract.json`。当前实现的 build/release Job
都由 `!inputs.dry_run` 限制，任何修改都不能去掉该边界。

### 14.5 Release 发布后没有 Docs PR

按顺序检查：

- 是否仍是 Draft；
- 是否为 prerelease；
- webhook 是否订阅 Release；
- delivery 是否是 `release.published`；
- Doc Agent 是否识别 `source_id=memos-cloud-cli`；
- 正式 mapping 是否已经部署而非只停留在未提交工作区；
- Tag range 是否完整；
- 质量报告是否失败关闭。

不要通过重复 Publish 或手工重发大量 webhook 盲目重试。先确定失败阶段，再对同一
delivery 做幂等 replay/修复。

### 14.6 官网把 CI 变更写成了产品能力

每条候选不仅要引用真实 commit，还必须至少引用一个“用户可感知”的 required
source ref。只引用 workflow、测试或发布自动化提交的条目会被拒绝。

---

## 15. 发布人员最终验收单

合并自动化 PR 前：

- [ ] actionlint 和全部 Node 测试通过。
- [ ] 检查 workflow 没有 Secret、权限或 reusable call 启动问题。
- [ ] 合成 artifact 明确标记为 `synthetic_contract_fixture`。
- [ ] 没有创建 Tag、Release、Docs PR 或部署。

第一次 dry-run 前：

- [ ] CLI 负责人已经选择 `<next-version>`。
- [ ] 三个版本源一致。
- [ ] `v1.0.6` 基线 Tag 经维护者批准并存在。
- [ ] 三个 repository Secret 已配置。
- [ ] Release webhook 可用。
- [ ] Doc Agent mapping 已持久化并部署。

真实发布前：

- [ ] dry-run 的 Tag range 和 target SHA 正确。
- [ ] `quality-report.json` 为通过。
- [ ] 中英文预览内容具体、准确、来源完整。
- [ ] 远端仍没有候选 Tag 和 Release。
- [ ] 发布提交已在当前 `main`。
- [ ] 精确确认词由发布负责人本人输入。

Publish Draft 前：

- [ ] Draft 标题、Tag、`What's Changed` 正确。
- [ ] Linux/Windows 资产符合仓库现有发布标准。
- [ ] 确认这次 Release 应当触发官网正式更新。

进入 production 前：

- [ ] MemOS-Docs PR 只改正确的 Plugin changelog 文件。
- [ ] pre 发布正常。
- [ ] 已等待 360 秒。
- [ ] gray 页面由 CLI 模块程序员检查通过。
- [ ] production 获得人工确认。

---

## 16. 本次改造明确不做什么

- 不替 CLI 负责人决定版本号。
- 不凭空创建未批准的 Tag。
- 不增加 macOS 或四平台矩阵。
- 不增加 SHA-256/checksum manifest。
- 不改变 npm 发布。
- 不改变 OSS 上传或 npm postinstall 下载逻辑。
- 不在 dry-run 中创建 GitHub Release。
- 不允许真实运行直接发布非 Draft Release。
- 不允许 Doc Agent 绕过 MemOS-Docs PR 和灰度检查。
- 不自动发布 production。
