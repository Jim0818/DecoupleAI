# Figure Layouts — 命名概念布局库（单一真相源）

> **唯一真相源（C4）**：「一个概念该用什么图形结构表达」的命名词汇表 + 高信号消歧决策表。
> 借鉴《图解 Skill》(Illustrated-Agent-Skills) `references/layouts/` 的 10 命名布局，补 3 个本系统缺口，落到本系统引擎。
>
> **与既有两轴的关系（三轴正交，勿混）**：
> - `mermaid_subtype`（architect figures[]）= **系统结构形状**（流程/时序/象限…，对齐 markdown-mermaid 24 类型）。
> - `visual_style`（visual-designer，[[../../agents/decouple-visual-designer/styles/style-library.md]]）= **美学渲染**（冷峻/蓝图/手稿…）。
> - **`layout`（本库）= 概念表达结构**（这个想法是「表面 vs 深层」还是「筛选漏斗」还是「A vs B」）。
>
> 一张图 = `layout`(概念怎么摆) × `engine`(用什么画) ×（mermaid 时叠 `mermaid_subtype`）×（栅格/卡片时叠 `visual_style`）。

---

## SVG V1 正式知识图布局表（6 个）

### SVG 成图优先原则与 renderer 状态

> **效果优先，不等于随意扩张**：SVG 能力的最小侵入边界是“不新增独立 Agent、不复制 token / schema / layout 真相源、不绕过 renderer”；但只要当前 SVG 会导致布局拥挤、主次不清、名实不一致或中文不可读，就必须优先修正构图，必要时明确 fallback 到 HTML / ui-view / Mermaid，而不是为了满足 `engine=svg` 产出一张低质量图。

`layout` 只回答“概念应该怎么表达”，不代表当前 SVG renderer 已经高质量支持。所有 layout 必须同时标注 `renderer_status`：

| renderer_status | 含义 | 执行动作 |
|---|---|---|
| `supported` | 当前 `scripts/render_svg_figure.py` 可稳定生成 | 可进入 SVG spec → renderer → self-check |
| `planned_svg` | 概念适合 SVG，但 renderer 尚未稳定支持 | 不直接产 SVG；先走 fallback，或先实现 renderer 再启用 |
| `fallback_only` | 当前更适合 HTML / ui-view / Mermaid / Excalidraw | 不强行塞进 SVG |
| `unsupported_svg` | 当前 SVG V1 不支持，且暂无近期实现计划 | 禁止临时手写不受控 SVG |

> 这 6 个 `layout_id` 是 SVG Figure Spec 的受控枚举。它们只用于
> `engine=svg` 的正式知识主图；高文字密度图仍走 HTML / ui-view，严格工程语义图仍走
> Mermaid。样式 token 与禁忌见 [[visual-design-system.md]] §11。

| layout_id | 中文 | 何时用（识别特征） | 视觉语法 | 首选引擎 | renderer_status | 兼容旧 layout |
|---|---|---|---|---|---|---|
| `layer_stack` | 分层堆栈 | 三层及以上的架构、记忆、能力、协议分层 | 纵向层叠、层级递进、强调主层；禁止平均堆块 | svg | `supported` | `hierarchical-layers` |
| `pipeline_flow` | 管线链路 | 输入—处理—输出、执行链、低分叉工作流 | 横向/分行阶段流，低交叉连线；主路径必须一眼可追踪 | svg | `supported` | `linear-progression` |
| `decision_tree` | 决策树 | 技术选型、条件分流、方案取舍 | 根节点→分支→终点；每条路径必须有条件和结论 | svg | `supported` | `tree-branching` |
| `mechanism_explainer` | 机制拆解 | 一个机制拆成 3–5 个组成部件或因果环节 | 中心概念 + 周边组件 + 因果关系；禁止散点拼贴 | svg | `supported` | `structural-breakdown` / `hub-spoke` |
| `before_after` | 前后结构 | 旧方案 vs 新方案、误区 vs 修正、重构前后 | 左右并置，共享对比轴，突出变化点；左右密度必须平衡 | svg | `supported` | `binary-comparison` |
| `comparison_matrix` | 结构对比 | 2–4 个对象的少量维度比较，文字密度可控 | 列式对比、少量强调；超过低密度阈值转 HTML | svg | `supported` | `comparison-matrix` |

**SVG V1 不支持**：`feedback_loop`、`system_map`、`timeline`、`radar`、`ecosystem_map`。
命中这些结构时按路由转 Canvas、Excalidraw、Mermaid 或 HTML，不临时手写不受控 SVG。

**强制效果门**：`renderer_status=supported` 只表示“能生成”，不表示“成图已合格”。Visual Designer 必须通过 `svg-figure-composer` 做 layout plan 和视觉复检；若出现布局拥挤、主次不清、edge spaghetti、节点平均铺满、中文不可读，即使 schema 通过也要重排或 fallback。

## 兼容布局表（13 个）

| layout_id | 中文 | 何时用（识别特征） | 视觉语法 | 首选引擎 | 本系统已有对应 |
|---|---|---|---|---|---|
| `binary-comparison` | 对比图 | A vs B、旧 vs 新、你以为 vs 实际 | 左右分屏，对称栏，中线 | ui-view `dual-column-compare` | ✅ 有 |
| `linear-progression` | 流程图 | 阶段演进 / 操作流程（无分叉） | 横向/纵向箭头链，节点编号 | mermaid flowchart LR | ✅ 拓扑 Pipeline |
| `hierarchical-layers` | 层级图 | 渐进披露 / 优先级 / L1-L2-L3 | 自上而下水平带，逐层缩进 | ui-view `hierarchy-tree` / svg | ✅ 拓扑 Layered |
| `hub-spoke` | 辐射图 | 核心 + 并列组成（X 由 A/B/C 构成） | 中心节点 + 放射枝 | mermaid mindmap / excalidraw | ≈ 拓扑 Router |
| `structural-breakdown` | 结构拆解 | 文件结构 / 组件标注 / 拆解剖面 | 主体 + 引线标注 callout | ui-view `dark-code-panel` / svg | ✅ 有 |
| `tree-branching` | 树形图 | 目录 / 决策分支（有「选哪条」） | 根→枝→叶，菱形决策点 | mermaid flowchart TD | 部分（flowchart） |
| `funnel` | 漏斗图 | **筛选 / 安全闸门 / KO 逐级淘汰** | 自上而下逐级收窄梯形 | svg / ui-view 新 block | ⛔ **缺**（贴 KO/质量门） |
| `winding-roadmap` | 路线图 | 全局导览 / 学习旅程（一条路向前） | 蜿蜒路径 + 里程碑站点 | svg / excalidraw | ⛔ **缺** |
| `iceberg` | 冰山图 | **表面 vs 深层 / 现象 vs 本质** | 水线分隔，上小下大 | svg / ui-view 新 block | ⛔ **缺**（贴「解耦本质」主线） |
| `cheat-sheet-card` | 速查卡 | 章节小结 / 知识回顾 / 可复用框架 | 网格卡片，标题+要点条 | ui-view `multi-card-dashboard` / svg-knowledge-card | ≈ 测评卡 / 可复用模板段 |
| `comparison-matrix` | 矩阵图 | ≥3 对象 × 多维度评分 | 行列表格 + 评分单元 | html_card V6 / ui-view；低密度 2–4 对象可转 svg `comparison_matrix` | ✅ V6 |
| `circular-flow` | 循环图 | 反馈环 / 飞轮 / 闭环 | 环形箭头回到起点 | mermaid flowchart（环） / excalidraw spiral | 部分 |
| `dashboard` | 仪表盘 | KPI / 多指标并置 | 分区指标格，大数字 | ui-view `multi-card-dashboard` | ✅ ui-view |

> ⛔ 三缺口已补入本表（funnel / winding-roadmap / iceberg）。优先实现顺序见 §四。

---


### 兼容布局 renderer_status 速查

| layout_id | renderer_status | 当前执行策略 |
|---|---|---|
| `binary-comparison` | `fallback_only` | 正式 SVG 用 `before_after`；高密度对比走 HTML / ui-view |
| `linear-progression` | `fallback_only` | 正式 SVG 用 `pipeline_flow`；复杂工程流程走 Mermaid |
| `hierarchical-layers` | `fallback_only` | 正式 SVG 用 `layer_stack`；高文字密度走 ui-view |
| `hub-spoke` | `fallback_only` | 简单机制图可改写为 `mechanism_explainer`；复杂网络走 Mermaid mindmap / Excalidraw |
| `structural-breakdown` | `fallback_only` | 简单拆解可改写为 `mechanism_explainer`；代码/文件结构走 HTML / ui-view |
| `tree-branching` | `fallback_only` | 正式 SVG 用 `decision_tree`；复杂分支走 Mermaid |
| `funnel` | `planned_svg` | 当前不直接产 SVG；先走 HTML / ui-view，待 renderer 实现后启用 |
| `winding-roadmap` | `unsupported_svg` | 当前走 Excalidraw / Canvas，不临时手写 SVG |
| `iceberg` | `planned_svg` | 当前不直接产 SVG；先走 HTML / ui-view 或 MJ 概念图，待 renderer 实现后启用 |
| `cheat-sheet-card` | `fallback_only` | 优先 ui-view `multi-card-dashboard` / HTML card |
| `comparison-matrix` | `fallback_only` | 低密度映射到 `comparison_matrix`；高密度走 HTML card V6 |
| `circular-flow` | `unsupported_svg` | 当前走 Mermaid / Excalidraw |
| `dashboard` | `fallback_only` | 当前走 ui-view `multi-card-dashboard` |

## 高信号消歧决策表（最易混三对，可机制化判定）

> 抽取「分叉/顺序/并列」三个信号即可定位，避免凭感觉选错 layout。

| 困惑 | 判据 | 选 |
|---|---|---|
| 决策 vs 辐射 | 有「选哪条 / 是 A 还是 B」 → 分叉信号 | `tree-branching` |
| 决策 vs 辐射 | 纯「X 由 A/B/C 组成」无取舍 | `hub-spoke` |
| 决策 vs 旅程 | 有分叉 | `tree-branching` |
| 决策 vs 旅程 | 一条路向前、无岔 | `winding-roadmap` |
| 辐射 vs 旅程 | 并列、无先后 | `hub-spoke` |
| 辐射 vs 旅程 | 顺序推进、有先后 | `winding-roadmap` |
| 对比 vs 矩阵 | 仅 2 对象 / 1 维度 | `binary-comparison` |
| 对比 vs 矩阵 | ≥3 对象 × ≥2 维度 | `comparison-matrix` |
| 漏斗 vs 层级 | 逐级**淘汰/收窄**（数量递减） | `funnel` |
| 漏斗 vs 层级 | 逐层**展开/深入**（信息递增） | `hierarchical-layers` |
| 冰山 vs 层级 | 强调「可见少 / 隐藏多」二分 | `iceberg` |
| 冰山 vs 层级 | 多级平铺、无表里二分 | `hierarchical-layers` |

---

## 三缺口的视觉语法（新实现参考）

### `funnel`（漏斗 — 贴 KO / 质量门 / 筛选）
- 自上而下 N 级梯形，每级宽度 ∝ 剩余数量；级间标「淘汰理由」。
- 用于：title-judge 9-rule KO、quality-gate 逐级筛、选题红海过滤。
- 引擎：svg-knowledge-card 或 ui-view 新增 block；MJ 片段 `top-down funnel with {N} narrowing stages, each stage labeled with a filter rule, items dropping out at each level, clean schematic`。

### `iceberg`（冰山 — 贴「现象 vs 本质」「解耦本质」主线）
- 水线分隔：水上 = 可见现象（小）；水下 = 底层结构（大，分层）。
- 用于：黑箱拆解、「你以为的 vs 真实机制」、表层 API vs 底层协议。
- 引擎：svg；MJ 片段 `iceberg cross-section, small visible tip above waterline labeled {现象}, large layered mass below labeled {本质结构}, cold blue water, scientific diagram`。

### `cheat-sheet-card`（速查卡 — 贴测评卡 / 可复用框架）
- 网格卡片，每卡 = 一个要点（标题 + 1-2 行）；整体可一屏速览。
- 用于：文末「可带走的思维工具」、Skill 测评卡、检查清单。
- 引擎：ui-view `multi-card-dashboard` 或 svg-knowledge-card。

---

## 落地接线（consumers）

| 环节 | 如何用 layout |
|---|---|
| architect `figures[]` | 每张图增 `layout` 字段（从本库取值），与 `mermaid_subtype` 并存：layout=概念表达，subtype=结构形状。正式主图优先使用 SVG V1 六类。见 architect output.schema.json。 |
| visual-designer | Step 2 引擎路由时，先判断图的主要价值，再按 figure 的 `layout` 取本库「视觉语法 + 首选引擎」；MJ 片段并入提示词。 |
| `scripts/render_svg_figure.py` | 仅消费 SVG V1 六类 `layout_id`，读取 `visual-design-system.md` §11 token 生成 `.svg`。PNG 截图由人工流程处理。 |
| ui-view-render / HTML figure | 渲染高文字密度、表格、Dashboard、清单和旧 13 布局中的 HTML 优先场景。 |

> 校验：architect figures[] 的 `layout` 取值必须 ∈ 本库 layout_id 枚举（schema enum 约束）。

---

## 四、缺口实现优先级（增量）

1. `iceberg` — 最贴「以算法理性解耦感性」主线，svg 先行。
2. `funnel` — 贴 KO / 质量门，svg 先行。
3. `cheat-sheet-card` — 复用 ui-view `multi-card-dashboard`，几乎零新增。

> winding-roadmap / circular-flow 暂留命名，按需再实现（C10 按当前规模建设，不预造）。
