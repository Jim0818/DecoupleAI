---
name: kb-bridge
description: |
  TextPicOS 与 AI-WIKI 的统一函数型桥接。输入 stdin JSON，必须包含
  `op`；输出 stdout JSON。仅供 Agent 程序化调用。
---

# kb-bridge

使用 `dispatch.py` 作为唯一入口；输入一个 JSON 对象：

```json
{"op": "read-exemplar", "account": "studio", "medium": "wechat", "top": 5}
```

从 `registry.py` 查看操作清单，从对应 handler 的模块文档读取入参与出参。
未知操作、缺少 `op` 或 handler 缺失均非零退出。外部操作先验证显式配置，
传入 `run_id` 时同时验证该原生运行身份；操作回执写入该运行。

## 配置

外部宿主必须设置 `TEXTPICOS_ROOT`，指向包含 `config/system/paths.json` 的当前项目。
项目内的源 bundle 可定位自身项目。访问知识库前，显式设置 `AI_WIKI_ROOT`
或 `TEXTPICOS_AI_WIKI_ROOT`；后者优先。系统维护模式不访问外部知识库。
本地 `read-topic-strategy` 无需配置知识库。

## 读取选题策略

使用 `read-topic-strategy` 的 `current` 模式。它只返回需由调用方实际读取的
账号 L1/L2 指针，不读取外部手册。策略不可用时返回 `not_available / not_read`；
必需调用非零退出，可选调用须显式传 `optional: true`。

## 发布单篇文章

仅在明确安排发布时调用 `publish-article`，传入单个 `article_path`：

```json
{"op": "publish-article", "article_path": "articles/pending/studio/classic-python/2026-11-18-check-columns_studio.md", "dry_run": true}
```

从文章 frontmatter 读取账号、栏目、slug 与 `run_id`。可选 `target_path` 必须是
配置知识库内的 Markdown 文件；省略时写入
`articles/published/<account>/<column>/<slug>/<article filename>`。
`force` 只允许替换不同的目标内容；每次调用仍校验主管运行已经完成、正文与
实际引用图片仍是本轮交付版本。若传入 `run_id`，必须与文章一致。

将 `dry_run` 设为 `true` 可先验证目标，且不写正文、目录、wiki 卡片或缓存。
正式调用会保留待发布源文件，复制正文与实际引用图片，将正文图片链接改到
目标 `visual/`，并更新项目 `resources/catalogs/` 中相应文章目录。
成功后生成 `04_wiki/articles/<account>/<column>/<slug>.md` 卡片，更新所引用节点的
`used_in`。重复调用先重新验证当前交付，再复用相同的增强结果；wiki 增强中断时
会清楚返回已发布路径，重新调用可继续完成。
