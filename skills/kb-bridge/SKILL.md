---
name: kb-bridge
description: |
  TextPicOS 与 AI-WIKI 的统一函数型桥接。输入 stdin JSON，必须包含
  `op`；输出 stdout JSON。仅供 Agent 程序化调用。
---

# kb-bridge

统一调用：

```json
{"op": "read-exemplar", "account": "studio", "medium": "wechat", "top": 5}
```

`dispatch.py` 是唯一入口，`handlers/` 保留各操作独立实现。读写能力、
入参和出参由各 handler 的模块文档定义；dispatcher 只做确定性路由。

支持的操作以 `registry.py` 为唯一清单。未知操作、缺少 `op` 或 handler
缺失均非零退出，不静默返回空。

`read-topic-strategy` 默认返回外部策略 `not_available / not_read`，只给出需由调用方
实际读取的账号 L1/L2 指针；必需调用非零退出，可选调用须显式传 `optional: true`。
它不读取外部手册，也不把旧 TOP1–6 当作当前策略。仅历史回放可显式指定
`strategy_mode: legacy_snapshot`，返回的历史观察不构成账号创作义务。
