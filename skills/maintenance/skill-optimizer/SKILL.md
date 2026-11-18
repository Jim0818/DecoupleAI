---
name: skill-optimizer
description: >
  审查并优化【已存在】的 Claude skill / agent —— 对单个 skill 或整个 skill 库做
  问题分析、优化建议、执行计划、适用范围判定，依据内置《如何写好 Skill 实战手册》
  与诊断清单。当用户说"优化这个 skill / 审查我的 skill / 这个 SKILL.md 怎么改进 /
  我的 skill 触发不准 / 帮我把这批 skill 体检一遍 / review/audit my skill" 时触发。
  不要在以下情况触发：从零创建一个新 skill（用 skill-creator）；只是想读懂或总结某个
  skill 的内容（直接 Read 即可）；运行/调试 skill 所实现的业务功能本身。
  Optimizes EXISTING skills: diagnosis, recommendations, execution plan, scope.
metadata:
  purpose: meta-skill for auditing & optimizing existing skills
  portable: true
---

# Skill Optimizer — 现有 Skill 的诊断与优化

把一个写好但"不太好使"的 skill，变成触发准、输出稳、可维护的 skill。
依据是同捆的实战手册 + 诊断清单，**但绝不教条照搬**——先看清 skill 的形态和它
所在项目的既有规范，再决定哪条建议适用。

## 何时用 / 何时不用

| 用 | 不用 |
|---|---|
| 优化/审查一个已存在的 SKILL.md | 从零创建新 skill → 用 `skill-creator` |
| 给一整个 skill 目录做体检 | 只想读懂某 skill 讲了啥 → 直接 Read |
| skill 触发不准 / 输出跑偏 / 太长 | 调试 skill 实现的业务功能本身 |
| 想要一份带优先级的优化执行计划 | 跑 eval/benchmark → `skill-creator` 的 eval 流程 |

> 与 `skill-creator` 的分工：creator 偏"造 + 迭代 + 跑 eval"；本 skill 偏
> **"对已存在的 skill 做诊断式审查 + 出可执行优化计划"**，可一次扫整库。两者可接力：
> 本 skill 出诊断 → 必要时交 creator 跑工程化评估。

## 工作流程（四阶段 = 四项能力）

```
Phase 0  适用范围与形态识别  →  Phase 1  问题分析  →  Phase 2  优化建议  →  Phase 3  执行计划
   (scope)                      (diagnosis)          (recommendations)      (execution plan)
```

每阶段都先产出、再进入下一阶段；不要跳过 Phase 0（判错形态/无视项目规范 = 给错建议）。

### Phase 0 — 适用范围与形态识别（scope）

1. **定位目标**：用户给的是单个 SKILL.md、一个 skill 目录、还是一个装了多个 skill 的父目录？
2. **判形态**（决定后续哪些维度关键）——读 [references/diagnostic-checklist.md](references/diagnostic-checklist.md) §「三形态」表：
   - 自动触发 skill（靠 description 匹配）→ 触发精准度是重点
   - 编排型 agent（被显式加载为 system prompt）→ 输出契约/判断框架是重点，触发词次要
   - 函数型桥接（程序化调用、常包脚本）→ I/O schema/探活/安全是重点，触发词无关
3. **探宿主项目规范（关键）**：在 skill 所在仓库**向上找** `CLAUDE.md`、`*-guide.md`、
   governance/ 目录、lint/audit 脚本、贡献规范。**读到的项目规则优先于手册**；
   冲突处在后续建议里显式标注"以项目规范为准"。
4. 产出一句话：**目标范围 + 形态 + 已知项目约束**。

### Phase 1 — 问题分析（diagnosis）

1. **跑确定性审计**（机械事实，C1 纪律：脚本只报结构、不判好坏）：
   ```bash
   python3 scripts/audit_skill.py <目标路径>          # 单个或整目录
   python3 scripts/audit_skill.py <父目录> --deep      # 递归整库
   python3 scripts/audit_skill.py <路径> --json        # 供程序消费
   ```
   它报：行数/超限、frontmatter 缺项、有无示例/表格/评估、疑似硬编码密钥、危险 shell 操作。
2. **LLM 判质量**：读 SKILL.md 全文，按 [references/diagnostic-checklist.md](references/diagnostic-checklist.md)
   A–K 维度逐项判断脚本判不了的"好不好"（description 是否笼统、示例是否覆盖分支、
   是否讲了 why、是否有反模式）。
3. **产出问题清单**：按影响**优先级排序**，每条给「症状 → 根因 → 依据手册章节」，
   并标 **必修（正确性/安全）** vs **可选（打磨）**。

### Phase 2 — 优化建议（recommendations）

每个问题给出：**改什么 + 为什么 + 依据哪条手册原则 + 改后预期效果**。

- 给具体改法（Before/After 片段、新 description 草案、要外置到 references/ 的内容清单）。
- **凡与 Phase 0 探到的项目规范冲突，显式标注并以项目规范为准**（例：项目用机制门管
  检查点，就不要建议加散文检查点）。
- 量化只用确定性指标（行数、缺字段、密钥命中=0）；**不给 skill 打加权小数总分**。

### Phase 3 — 执行计划（execution plan）

产出一份可直接执行的计划（结构见下「输出格式」）：Context → 分阶段改动（含具体文件）
→ 验证方法 → 明确不在范围内的事。改动多文件时，把重复模式描述一次 + 列代表文件，
不逐行罗列。计划默认**先不动手**，等用户确认。

## 核心原则（贯穿四阶段）

1. **先形态后建议**：判错形态 = 给错建议（给函数型桥接优化"触发词"毫无意义）。
2. **项目规范 > 手册**：手册是通用最佳实践，不是教条；宿主项目的硬约束永远优先。
3. **机制 > 文字**：能用脚本/hook/schema 机制保证的，别用散文反复叮嘱。
4. **稳定 > 花哨**：示例的价值是让输出稳定；排序+理由+硬判定，少用主观加权分。
5. **更短更少**：默认建议精简；增内容要举证，减不需要。

## 输出格式

### 问题分析报告
```
## {skill 名} 诊断报告
- 形态：{自动触发 / 编排型 agent / 函数型桥接}
- 适用范围：{一句话}
- 已知项目约束：{读到的规范，或"未发现"}

### 必修问题（按优先级）
1. [维度X] 症状 → 根因 → 依据手册 §Y → 修复方向
2. ...

### 可选优化
- ...

### 机械审计摘要（audit_skill.py）
🔴 ERROR n  🟡 WARN n  🔵 INFO n（关键项列出）
```

### 优化执行计划
```
## {skill} 优化执行计划
### Context（为什么）
### 阶段改动
  - 改 {file}：{改什么 + 为什么 + 依据}
  - 新建 {file}：{用途}
### 与项目规范的取舍（如有冲突，标明以谁为准）
### 验证
  - 跑 audit_skill.py 确认 ERROR=0
  - {触发评估 / 输出对比 / 其他}
### 不在本计划内
```

## Few-Shot 示例（一个最小诊断片段）

**输入**：某 skill 的 frontmatter
```yaml
name: migrate
description: 处理代码迁移
```
**诊断输出**：
```
形态：自动触发 skill（靠 description 匹配）→ 触发精准度是重点
🔴 必修-A 触发：description 笼统（"处理代码迁移"）。根因：无技术关键词/起点终点/
   使用场景，AI 无法判断何时该用，且易与其他迁移类 skill 抢触发。依据 §3.1 + 反模式2。
   修复 → 例：
   description: >
     将项目中的旧版 HTTP 客户端迁移到新版统一请求库。适用于使用了 old-http-client、
     需替换为 unified-httpclient 的场景，含 import 替换/参数适配/错误处理改造。
     不要在新建客户端或非迁移类重构时触发。
🔵 可选-A：补反例触发（"不要在…"）已含在上方草案，提升与近义 skill 的区分度。
```

## 参考资料（按需加载）

| 文件 | 何时读 |
|---|---|
| [references/diagnostic-checklist.md](references/diagnostic-checklist.md) | Phase 0 判形态、Phase 1 逐维诊断（每次都用） |
| [references/skill-writing-handbook.md](references/skill-writing-handbook.md) | 需要某条原则的完整论据/示例时（手册全文，腾讯团队+Anthropic 实战经验） |
| `scripts/audit_skill.py` | Phase 1 确定性机械审计 |
