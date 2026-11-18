---
name: skill-optimizer-native
description: >
  TextPicOS 专用的 Skill、Agent 与函数型桥接治理入口。新建、修改或审计本仓库的
  SKILL.md、执行契约、评估用例及相关脚本时使用；按现行宪法诊断问题、实施修复并验证。
  写文章或运行创作流水线时不使用；跨项目通用 Skill 优化使用 skills/skill-optimizer/。
metadata:
  role: TextPicOS Skill·Agent·Tool 生命周期前门
---

# TextPicOS Skill·Agent·Tool 生命周期前门

本 Skill 负责把请求路由到现行真相源，并完成诊断、修改和验证。事实的所有权与路径以
`workflows/governance/source-registry.yaml` 为准；不要在这里复制规则、阶段或阈值。

## 先确定任务与执行形态

1. 区分新能力、既有能力修改、只读审计。用户要求修改时，诊断后直接实施；仅在缺少会改变方案的关键输入时询问。
2. 识别编排型 Agent、自动触发 Skill 或函数型桥接；按 [撰写规范 §0](references/authoring-conventions.md) 选择相应检查点。
3. 读取目标及其调用方、消费者、Schema、Runtime、Capsule 和已有评估；只加载本次任务相关的文件。
4. 新增能力先按 [治理宪法 §5](../../../docs/AI-Native治理宪法.md) 举证准入。重构默认路径上的存量单元时，按 C6/C15 复审边际贡献；兼容层按 C16 标明退出条件。

## 诊断与建议

- 机械事实：运行 `python3 skill-optimizer-native/scripts/audit_skill.py <目标> --gate`。它检查结构与可机械发现的风险；缺失目标会失败。生产 Agent 的系统门仍由 `bash scripts/audit.sh` 执行。
- 判断问题：按 [撰写规范](references/authoring-conventions.md) 和按需加载的 [诊断清单](references/diagnostic-checklist.md) 核对目标任务、输入、输出、失败语义、上下文与成本。判断型 Agent 的 `python3 scripts/eval_skill.py agents/{name}` 只生成评估工单；`--validate-only` 只验证用例结构，不等于行为通过。
- 按影响排序报告「症状 → 根因 → 证据 → 修复」。区分正确性或安全问题与可选改进。语义判断用理由、定位和硬 KO，不给加权小数总分（C8）。
- 先找现有 mode、profile、脚本、reference 或 Schema 能否承载修复。新 Gate、Phase、常驻 Prompt 和独立 Agent 都须经过宪法准入；能用机制验证的规则交给机制（C1/C2/C6）。

## 实施与验证

1. 修改事实的唯一真相源，并更新确实消费该事实的指针、用例或执行器。Schema 是输出结构的机器契约；不要要求每个 Agent 都在 SKILL.md 复制一份完整输出模板。
2. 结构变更按 [.agents/skills/doc-sync/SKILL.md](../../../.agents/skills/doc-sync/SKILL.md) 检查同步义务；`.claude/skills/` 是生成镜像。不要凭记忆改计数或阶段图。
3. 运行与改动相关的脚本测试、Schema 校验或行为评估。修改 Codex Skill 本身时还需运行可用的 Skill Creator 校验；本地结构审计不替代平台校验。检查引用和触发边界。
4. 结构变更及宣称完成前运行 `bash scripts/audit.sh`；任一 FAIL 当场修复，不带病合并。若既有失败超出本次可安全修复的范围，说明审计未通过及具体阻碍，不伪称全 PASS。
5. 报告改了什么、验证结果和剩余限制。只做审计的请求输出可执行建议，不擅自修改。

## 按需参考

| 资源 | 读取时机 |
|---|---|
| [撰写规范](references/authoring-conventions.md) | 新建、修改或审计本仓库 Skill/Agent |
| [诊断清单](references/diagnostic-checklist.md) | 需要逐维定位问题或比较方案 |
| [通用实战手册](references/skill-writing-handbook.md) | 需要跨项目论据或示例；本仓库的宪法、契约和预算优先 |
| `workflows/governance/source-registry.yaml` | 确认事实所有权与现行路径 |
| `workflows/governance/complexity-budget.yaml` | 确认行数、阶段和常驻上下文预算 |

本仓库工作使用本 Skill；可分享版 `skills/skill-optimizer/` 面向跨项目场景。两者不要互相复制本地治理规则。
