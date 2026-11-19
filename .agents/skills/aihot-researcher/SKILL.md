---
name: aihot-researcher
description: >
  TextPicOS 的可选 AI 新闻线索源。仅在 research/discover 确实需要近期动态、
  用户指定热点或明确选择本工具时，从 aihot 获取一页线索。已有选题、常青教程、
  文档核实不默认调用；不评分，不决定账号适配或代替原始来源核验。
---

# AI Hot Researcher

为当前研究任务补充新闻线索。按账号 L1/L2 和所选范围判断是否值得继续，
选题方法见项目 `skills/research/references/discovery.md`。

## 调用

在项目根目录运行：

```bash
python .agents/skills/aihot-researcher/fetch.py
```

按当前任务需要显式设置 `--mode selected|all`、`--window-hours`、`--take`。
默认窗口、单次条数、超时和响应字节预算由 [config.json](config.json) 的 `fetch`
定义。只请求一页，不为补足数量自动扩大时窗或重试，不绕过 DNS 或访问限制。

`fetch.py` 输出 JSON，保留标题、摘要、原始链接、来源时间与抓取时间。摘要来自
聚合服务，`verification: source_not_checked` 表示尚未读取原始来源。即使有热度、
社区推荐或多家转载，也不能据此确认事实、读者需求、作者体验或账号适配。

## 结果与降级

- `ok`：取得一条或多条线索。逐条判断其相关性，必要时打开原始发布、文档或仓库。
- `empty`：请求成功且没有线索。它是有效结果，不能改写成“服务故障”。
- `unavailable`：网络、超时或 HTTP 失败；`invalid_response`：返回结构不可用。
  两者都非零退出并保留明确状态。说明缺口后，可按任务选择官方 RSS、GitHub
  Releases 或网页检索；降级来源的结果另行注明，不能冒充 aihot 返回。
- `invalid_config`：本地参数或配置错误；修复后再调用。

一条有价值的线索足够继续；也允许没有候选。不输出固定数量的选题卡，不以
行业影响、源码深度、抽象程度或“亲测”作为所有教程的入选前提。主管只接收本次
真正有用的线索、链接、日期和下一步证据缺口；不移交到旧阶段或旧三问硬筛。

## 历史兼容

`score.py`、`dim_scores.json` 与 `config.json` 的 `legacy_scoring` 只供明确的
历史评分回放。直接调用 `score.py` 会标记 `legacy_replay`；其原有格式与算术保留
给旧读取者及 `test_score.py`。当前 discover 不调用它、不消费分数，也不据此扩抓。
这些兼容文件可在历史读取者不再依赖旧格式时一起退出；需要回退时使用原始保存
输入回放，不把历史策略重新设为当前默认。故障核查见 [API验证手册.md](API验证手册.md)。
