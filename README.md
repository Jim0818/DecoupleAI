# DecoupleAI

<p align="center">
  <strong>以算法的理性，解耦 AGI 的感性</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
  <a href="https://github.com/Jim0818/DecoupleAI/tree/main/my-skills"><img src="https://img.shields.io/badge/skills-1-orange" alt="Skills"></a>
</p>

DecoupleAI 是一套 **AI 辅助内容生产系统**——18 个专用 Agent（AI 工作角色）协作，覆盖从选题研究、架构设计、正文撰写、视觉设计到质量审查的完整流水线。支撑三个微信公众号的日常运营。

但它不止于此。**my-skills/** 目录下是面向所有 Claude Code 用户的通用工具——目前第一款是给 AI 技能做"体检"的诊断工具。

---

## 架构概览

```
选题策略 ──→ 解耦分析 ──→ 架构蓝图 ──→ 正文撰写 ──→ 精炼 ──→ 标题评选
    │                                                  │
    └──────────── 视觉设计 · 质量审查 · 终审 ──────────┘
```

### 18 个生产 Agent

| Agent | 职责 |
|---|---|
| **Researcher** | 选题策略、竞品分析、KB 检索 |
| **Decoupler** | 三分支路由、论证结构拆解 |
| **Architect** | 章节规划、蓝图锁定 |
| **Writer** | 8 段叙事正文产出 |
| **Refiner** | 语言打磨、去 AI 味 |
| **Hook Master** | 12+ 标题候选生成 |
| **Title Judge** | 9 规则 KO + 8 维定性比较 |
| **Visual Designer** | HTML 卡片、MJ 提示词、概念图 |
| **Reviewer** | 硬门控逐项核查 |
| **Chief Editor** | 终审 PASS/REVISION/REJECT |
| **Style Analyst** | 风格指纹提取与适配 |
| **Workflow Manager** | Auto mode 调度与事件日志 |
| **Case Scout / Architect / Executor / Recorder** | CMM 案例制造机 |

### 5 条工作流

| 工作流 | 账号 | 特点 |
|---|---|---|
| WF1 主流水线 | DecoupleAI 主号 | 深度结构分析、认知冲击 |
| WF2 Studio | 数据STUDIO | 工程实现、代码实操 |
| WF3 CMM | 跨账号 | 案例构建（个人/团队/商业） |
| WF4 IntelliFuture | 智性未来 | 面向普通人的 AI 科普 |
| WF5 SVP | 短视频 | 孵化中 |

---

## 🧰 my-skills/ — 拿走即用

这些是**独立于主流水线**的通用工具，任何 Claude Code 用户都能用。复制到 `~/.claude/skills/` 即可。

<!-- SKILLS_INDEX_START -->
### [skill-optimizer](my-skills/skill-optimizer/)

> Skill Optimizer — 现有 Skill 的诊断与优化

审查并优化【已存在】的 Claude skill / agent —— 对单个 skill 或整个 skill 库做 问题分析、优化建议、执行计划、适用范围判定，依据内置《如何写好 Skill 实战手册》 与诊断清单。当用户说"优化这个 skill / 审查我的 skill / 这个 SKILL.md 怎么改进 / 我的 skill 触发不准 / 帮我把这批 skill 体检一遍 / review/audit my skill" 时触发。 不要在以下情况触发：从零创建一个新 skill（用 sk

```bash
# 安装
cp -r my-skills/skill-optimizer ~/.claude/skills/
```


<!-- SKILLS_INDEX_END -->

---

## 快速开始（如果你对 DecoupleAI 流水线本身感兴趣）

整个系统靠 **CLAUDE.md**（项目治理宪法）+ 18 个 Agent SKILL.md 驱动。入口：

```bash
git clone git@github.com:Jim0818/DecoupleAI.git
```

阅读顺序：
1. [`CLAUDE.md`](CLAUDE.md) — 治理宪法与操作摘要
2. [`workflows/governance/orchestration-protocol.md`](workflows/governance/orchestration-protocol.md) — 相图与路由
3. [`agents/`](agents/) — 各 Agent 的 SKILL.md（输入/output schema）

> 注意：DecoupleAI 主仓库的完整 pipeline 代码不在 GitHub 上（涉及运行时配置和外部知识库桥接）。此处开源的是 **Agent 系统的骨架文档和 my-skills 通用工具**。

---

## 仓库结构

```
DecoupleAI/
├── README.md              ← 你在这
├── LICENSE                (Apache 2.0)
├── CLAUDE.md              治理宪法（核心入口）
├── agents/                 18 个 Agent 的 SKILL.md
├── workflows/              工作流定义、治理门控、路由表
├── platforms/              三账号专属配置与质量门覆盖
├── my-skills/              ★ 通用工具，拿走即用
│   └── skill-optimizer/    AI 技能诊断器
├── docs/                   运维备忘与参考文档
└── .claude/                项目级 settings/hooks
```

---

## 贡献

- **my-skills/**：欢迎 PR。如果你写了一个好用的通用 Skill，提 PR 到 `my-skills/<your-skill>/`，格式参照 `skill-optimizer`（SKILL.md + references/ + scripts/）。
- **Agent pipeline**：目前为私有运维阶段，Agent 骨架文档仅供学习和参考。

---

## License

[Apache 2.0](LICENSE) © 2026 Jim0818
