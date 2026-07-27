## Changelog

### Improved

- **Release safety checks**: Validates evidence, assets, and immutable publication metadata before a CLI release can write externally.

<!-- doc-agent-release-notes-json
{
  "schema": "memos.plugin.release_notes.v1",
  "items": [
    {
      "category": "Improved",
      "text_cn": "**CLI 发布安全检查**：发布前校验真实变更证据、四平台资产与不可变发布元数据，失败时保留可检查错误。",
      "text_en": "**CLI release safety checks**: Validates real change evidence, four-platform assets, and immutable publication metadata while preserving inspectable failures.",
      "source_refs": [
        "23060daa18713bec399679737e4df2ce5c18c934",
        "dc2bbc8b93b3b3afaaa9ebd2ebd7b67ce43d23e2"
      ]
    }
  ],
  "coverage": {
    "needs_review": false
  }
}
-->

<!-- doc-agent: source-id=memos-cloud-cli -->
