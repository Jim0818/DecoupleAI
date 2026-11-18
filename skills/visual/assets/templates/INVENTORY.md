# Templates Inventory — V1-V10 占位符与白底配色规范

> 每个模板列出：对应人格、必填占位符、选填占位符、配色 hex、版式规格。
> 占位符标签：**R** = required（缺失即视为不合格）；**O** = optional（可用 fallback 默认值）。
> V1-V10 均为白色背景系列；标准模板是基准，不是上限。VD 可按具体文章结构新增 `custom-{purpose}.html` 卡片或 `figure-{layout-or-purpose}.html` 过程图，但必须保持白底体系与渲染契约。

---

## V1 White — 解剖室感

- **文件**：`v1-dark-mode.html`
- **画布**：560 × 自适应
- **配色**：`#f4f6f8`（外底）/ `#ffffff`（卡身）/ `#f8fafc`（区块底）/ `#0f172a`（主文字）/ `#2563eb` `#059669` `#7c3aed`（L1/L2/L3 三色）
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 | 缺失 fallback |
|---|---|---|---|---|
| TITLE | R | 6-20 字 | structural_model.essence 或 H1 | — |
| DESC | R | 20-50 字 | 文章首段摘要 | — |
| ESSENCE | R | ≤30 字 | structural_model.essence | TITLE 重写为本质句 |
| LAYER_1_NAME / LAYER_2_NAME / LAYER_3_NAME | R | 4-10 字 | layers[i].name | — |
| LAYER_{1,2,3}_DESC | R | 25-60 字 | layers[i].desc | — |
| LAYER_{1,2,3}_TAG_{A,B,C} | R | 2-6 字 | layers[i].tags（取前 3） | 缺失则填同 NAME 同义短语 |
| LAYER_{1,2,3}_INPUT / OUTPUT | R | 2-15 字 | layers[i].input/output | — |
| INSIGHT_1 / INSIGHT_2 / INSIGHT_3 | R | 20-50 字 | 文章中可独立成图的核心断言或 Claim | — |
| COLUMN | R | — | input.column | "DecoupleAI" |
| DATE | R | YYYY.MM | input.publish_date | 当月 |

---

## V2 Light — 实验室感

- **文件**：`v2-light-mode.html`
- **画布**：540 × 自适应
- **配色**：`#dde1e8`（外底）/ `#fefefe`（卡身）/ `#f0fdf4`（真相区）/ `#16a34a`（绿 accent）/ `#0f172a`（金句深底）
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 |
|---|---|---|---|
| COLUMN | R | — | input.column |
| TITLE | R | 6-18 字 | H1 |
| SUBTITLE | R | 15-40 字 | 副标题或首段提炼 |
| MISCONCEPTION | R | 20-60 字 | 文章中"误解/迷思"段 |
| TRUTH | R | 20-60 字 | 文章中"真相/本质"段 |
| STEP_1_TITLE / STEP_2_TITLE / STEP_3_TITLE | R | 4-10 字 | layers 或正文步骤 |
| STEP_{1,2,3}_DESC | R | 20-50 字 | — |
| METAPHOR | R | 20-50 字 | 正文类比段 |
| INSIGHT | R | 15-40 字 | hooks.gold_sentence |
| DATE | R | YYYY.MM | — |

---

## V3 Insight — 极简洞察

- **文件**：`v3-one-insight.html`
- **画布**：500 × 自适应
- **配色**：`#e8eaed`（外底）/ `#ffffff`（卡身）/ `#f8fafc`（洞察块）/ `#60a5fa`（高亮）/ stat 三色 `#2563eb` `#059669` `#7c3aed`
- **⚠️ hero-icon 占位需手动替换**：`<div class="hero-icon-wrap">` 中的 `src="../logo.png"` 必须替换为微信公众号素材库 mmbiz.qpic.cn 直链才能在公众号正文中正常显示。详见模板内 HTML 注释。
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 |
|---|---|---|---|
| COLUMN / DATE | R | — | input |
| LOGO | R | — | `../logo.png`（固定） |
| TITLE | R | 6-14 字 | H1 |
| SUBTITLE | R | 20-50 字 | 提炼 |
| INSIGHT_MAIN | R | 5-20 字 | 金句前段 |
| INSIGHT_HIGHLIGHT | R | 4-12 字 | 金句中要强调的短语（被高亮） |
| INSIGHT_TAIL | R | 5-20 字 | 金句后段 |
| STAT_{1,2,3}_VALUE | R | 数字 | 文章中数据点 |
| STAT_{1,2,3}_UNIT | R | 1-4 字 | %、x、ms、维 |
| STAT_{1,2,3}_LABEL | R | 6-14 字 | 数据含义 |
| ONE_RULE | R | 20-50 字 | 文章核心法则/规则 |

---

## V4 Map — 系统图谱

- **文件**：`v4-system-map.html`
- **画布**：580 × 自适应
- **配色**：同 V1 白底结构系，多 `α/β/γ/δ` 变量槽
- **占位符**：

| 名称 | 必/选 | 来源 |
|---|---|---|
| TITLE / DESC / ESSENCE | R | 同 V1 |
| LAYER_{1,2,3}_NAME / DESC / TAG_{A,B,C} / INPUT / OUTPUT | R | 同 V1 |
| VAR_A / VAR_B / VAR_C / VAR_D | R | structural_model.variables[0..3].meaning（如不足 4 个，剩余从 layers 关键参数补）。**单个值上限 22 字**，超出截断并加省略号。 |
| COLUMN / DATE | R | input |

---

## V5 Poster — 概念海报

- **文件**：`v5-poster.html`
- **画布**：420 × ≥600（竖版）
- **配色**：`#f4f6f8`（外底）/ `#ffffff`（海报）/ 蓝色轻量光晕
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 |
|---|---|---|---|
| COLUMN | R | — | input |
| CATEGORY | R | 4-10 字 | 栏目+话题（如"基石解耦 · Token"） |
| LOGO | R | — | `../logo.png`（固定） |
| TITLE | R | 6-12 字 | 标题（含力量感） |
| SUBTITLE | R | 20-50 字 | 副标题 |
| THESIS | R | 20-50 字 | 文章核心论点 |
| BULLET_1..BULLET_4 | R for available items | 12-30 字 | hooks.tldr 2-4 条；不要为空缺项补伪第三条 |
| DATE | R | YYYY.MM.DD | input |
| AUTHOR | O | — | "DecoupleAI" |

---

## V6 Matrix — 对比矩阵

- **文件**：`v6-comparison-matrix.html`
- **画布**：660 × 自适应
- **配色**：浅底 `#fff` / 蓝绿 accent / 评分四色（best/good/ok/bad）
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 |
|---|---|---|---|
| TITLE / DESC | R | — | H1 + 副标 |
| COL_0 | R | 2-4 字 | "工具/方法" |
| COL_1 / COL_2 / COL_3 / COL_4 | R | 2-6 字 | 4 个评估维度 |
| ROW_{1,2,3,4}_NAME | R | 2-12 字 | 被对比对象名 |
| ROW_{i}_C{1..4} | R | ≤8 字 | 单元格短描述 |
| VERDICT_BEST / VERDICT_AVOID / VERDICT_LOGIC / VERDICT_RULE | R | 15-40 字 | 文章末段结论 |
| COLUMN / DATE | R | — | input |

> **注意**：模板将各 ROW 的进度条 `style="width:..%"` 写死，需要根据真实评分**手动修改 inline width 与 fill class**（best/good/ok/bad）。这是占位符之外的"结构性填充"，参见 template-extraction-rules.md §6。

---

## V7 Slides — 幻灯片组

- **文件**：`v7-slide-deck.html`
- **画布**：4 张 16:9（约 720×405 单张）
- **占位符**：4 组步骤，每组 `STEP_{i}_TITLE` + `STEP_{i}_DESC`（必），加 TITLE / SUBTITLE / MISCONCEPTION / TRUTH / 3 组 STAT / INSIGHT_*  / COLUMN
- **使用要点**：4 张幻灯片建议序列：① 封面（TITLE+SUBTITLE）② 误解/真相（MISCONCEPTION/TRUTH）③ 步骤拆解（STEP_*）④ 金句+数据（INSIGHT/STAT）

---

## V8 Infographic — 信息长图

- **文件**：`v8-infographic.html`
- **画布**：竖版长图（适配小红书 3:4 / 微信单图）
- **占位符并集**（汇总 V2 + V3 元素）：TITLE / SUBTITLE / LOGO / COLUMN / DATE / MISCONCEPTION / TRUTH / 3×STEP_TITLE+DESC+TAG / METAPHOR / INSIGHT_MAIN+HIGHLIGHT+TAIL / 3×STAT_VALUE+UNIT+LABEL
- **STEP_TAG**（V8 特有）：4-8 字关键词标签，从 layers[i].tags[0] 取

---

## V9 Code Engineering — 代码工程风

- **文件**：`v9-code-engineering.html`
- **账号**：`account_id=studio` 专属（GitHub藏经阁 / Agent×协议工程 / Python工程师进化论 / AI Infra底层 / AI Coding×工作流 栏目）
- **画布**：560 × 自适应
- **配色**：`#f4f6f8`（外底）/ `#ffffff`（卡身）/ `#f8fafc`（区块底）/ `#059669`（绿 accent）/ `#FF8C42`（橙 accent）/ `#2563eb`（蓝辅助）
- **字体**：`JetBrains Mono` / `Fira Code`（等宽），中文回退 PingFang SC
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 | 缺失 fallback |
|---|---|---|---|---|
| TITLE | R | 6-20 字 | H1 | — |
| SUBTITLE | R | 15-40 字 | 首段提炼 | — |
| COLUMN | R | — | input.column | — |
| DATE | R | YYYY.MM | input.publish_date | 当月 |
| PAIN_POINT | R | 20-60 字 | 文章"没有这个库你要写…"段落 | — |
| CODE_TITLE | R | 10-30 字 | 代码块标题或功能描述 | — |
| CODE_LANG | R | 2-10 字 | "python" / "bash" / "python+bash" | "python" |
| CODE_SNIPPET | R | ≤20行 | 文章中最能体现主题的核心代码片段（HTML-escaped；可含 `<span class="kw/fn/str/cm/num/cls/dec">` 语法高亮标签） | — |
| LIB_1_NAME / LIB_2_NAME / LIB_3_NAME | R | 2-15 字 | 文章中 3 个核心库名 | — |
| LIB_1_ROLE / LIB_2_ROLE / LIB_3_ROLE | R | 8-20 字 | 每个库解决的核心问题（≤20字） | — |
| LIB_1_CMD / LIB_2_CMD / LIB_3_CMD | O | ≤30 字 | `pip install xxx` | `pip install {NAME}` |
| CORE_INSIGHT | R | 20-55 字 | 文章核心金句或工程洞察 | — |
| STAT_1_VALUE / STAT_1_UNIT / STAT_1_LABEL | R | 数字 / 1-4字 / 6-14字 | 文章中数据点（如"7个库" / "200行" / "省去样板代码"） | — |
| STAT_2_VALUE / STAT_2_UNIT / STAT_2_LABEL | R | 同上 | — | — |

> **CODE_SNIPPET 填写规则**：先将代码 HTML-escape（`<`→`&lt;` 等），再选择性包裹语法高亮 span。最多 20 行，超出截断并在末尾加 `<span class="cm">  # ... 省略 N 行</span>`。

---

## V10 AI Visual Office — AI 办公视觉风

- **文件**：`v10-ai-visual-office.html`
- **账号**：`account_id=studio` 历史模板（《AI视觉办公》栏目已退役；V10 仅用于存档文章，不再新建）
- **画布**：540 × 自适应
- **配色**：`#f0f2f5`（外底）/ `#ffffff`（卡身与 header）/ 紫色 accent `#7c3aed`；Before 红 `#fef2f2` / After 绿 `#f0fdf4`；Prompt 紫 `#faf5ff`
- **字体**：系统无衬线（Inter / HarmonyOS Sans / SF Pro Display）
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 | 缺失 fallback |
|---|---|---|---|---|
| TITLE | R | 6-20 字 | H1 | — |
| SUBTITLE | R | 15-40 字 | 首段提炼 | — |
| COLUMN | R | — | input.column | "AI视觉办公" |
| DATE | R | YYYY.MM | input.publish_date | 当月 |
| BEFORE_LABEL | O | 2-6 字 | "手工" / "传统方式" | "手工" |
| AFTER_LABEL | O | 2-6 字 | "AI 生成" | "AI 生成" |
| BEFORE_DESC | R | 20-60 字 | 文章"以前怎么做"段落 | — |
| AFTER_DESC | R | 20-60 字 | 文章"现在用 AI 怎么做"段落 | — |
| PROMPT_LABEL | R | 4-12 字 | "Prompt 模板" / "核心提示词" | "Prompt 模板" |
| PROMPT_CONTENT | R | 50-200 字 | 文章中可直接复用的 Prompt 模板（支持 `<span class="prompt-var">` 标注变量占位符） | — |
| STEP_1_TITLE / STEP_2_TITLE / STEP_3_TITLE | R | 4-12 字 | 文章操作步骤标题 | — |
| STEP_1_DESC / STEP_2_DESC / STEP_3_DESC | R | 15-40 字 | 每步骤简述 | — |
| TIP_1 / TIP_2 | O | 10-30 字 | 文章踩坑或调优技巧 | 两者均空时删除整个 `.tips-section` 节点 |
| RESULT_DESC | R | 20-50 字 | 文章效果描述或读者预期收益 | — |

---

## EX — Excalidraw 论证图

- **产物类型**：`.excalidraw` JSON
- **触发方式**：由 persona-decision-matrix §三-b 决定（并行于 V1-V10，不替代 HTML 卡）
- **落盘路径**：`articles/pending/visuals/{run_id}/{slug}-argument-diagram.excalidraw`
- **技能参考**：`.claude/skills/excalidraw-diagram-skill/SKILL.md`（颜色 palette 读 `references/color-palette.md`）

| 规格项 | 要求 |
|--------|------|
| roughness | 0（clean mode，默认）|
| 图形模式 | 按 persona-decision-matrix §三-b 推荐选型（Assembly Line / Multi-zoom / Side-by-Side / Tree / Fan-out）|
| container 比例 | <30% 文本元素有容器（其余 free-floating）|
| 源码验证 | `.excalidraw` 必须落盘并列入 `files_written[]`；PNG 截图由人工流程处理 |
| 品牌标注 | 右下角添加 free-floating 文字 "DecoupleAI" 或 "数据STUDIO"（按 account_id）|

---

## 过程图模板（figures/，行内 HTML 引擎）

> **作用域**：架构师 `figures[].engine == "html_card"` 时使用。库存模板覆盖常见 layout；若当前文章需要不同过程结构，VD 可新增同规格白底 HTML 模板，文件名建议 `figure-{layout-or-purpose}.html`。
> 与 V1-V10 卡片**不同角色**：卡片是 standalone 海报；figure 是嵌入文章正文的过程图，宽度更宽（720-760）、品牌 footer 更小。
> 输出：只交付 `{fig.html}` 源文件；PNG 截图由人工流程处理。
> 占位符抽取规则见 [template-extraction-rules.md](../template-extraction-rules.md) §9。

### figure-iceberg.html — 冰山（表象 vs 本质）

- **文件**：`figures/figure-iceberg.html`
- **画布**：720 × 自适应
- **layout**：iceberg
- **配色**：浅蓝水面 `#eff6ff` / 白底深层 `#ffffff + #f8fafc`；三层 accent `#58a6ff / #3fb950 / #bc8cff`
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 |
|---|---|---|---|
| FIGURE_CAPTION | R | 6-20 字 | `figures[i].caption` 或 architect purpose |
| SURFACE_LABEL | R | 2-6 字 | 表象侧总标签（如「可见现象」「用户感受」） |
| SURFACE_TITLE | R | 6-18 字 | 表象侧一句话（如「RAG 查不准」） |
| SURFACE_DESC | R | 15-40 字 | 表象侧补充说明 |
| DEPTH_{1,2,3}_LABEL | R | 4-10 字 | 三层底层结构的层级标签（如「L1 · 查询」） |
| DEPTH_{1,2,3}_TITLE | R | 6-18 字 | 各层标题 |
| DEPTH_{1,2,3}_DESC | R | 15-40 字 | 各层一句话说明 |

### figure-funnel.html — 漏斗（筛选 / 质量门）

- **文件**：`figures/figure-funnel.html`
- **画布**：720 × 自适应
- **layout**：funnel
- **配色**：白底 `#ffffff` / 浅灰 stage `#f8fafc`；五级 stage 宽度 100%/82%/64%/46%/30%；accent 顺序 `#58a6ff → #58a6ff → #3fb950 → #bc8cff → #FF8C42`
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 |
|---|---|---|---|
| FIGURE_CAPTION | R | 6-20 字 | architect purpose 或层级描述（如「Title Judge · KO 九条」） |
| FIGURE_TITLE | R | 6-18 字 | 漏斗主题（如「冠军标题筛选流」） |
| STAGE_{1..5}_COUNT | R | 1-4 字 | 该级剩余数量（如「100」「3」） |
| STAGE_{1..5}_NAME | R | 4-12 字 | 该级名称 |
| STAGE_{1..5}_DESC | R | 8-20 字 | 该级一句话 |
| DROP_{1..4}_REASON | O | ≤14 字 | 级间淘汰理由（不填则隐藏不影响版式） |

> 仅 4-5 级常用；只用 3 级时把 stage_4/5 + drop_3/4 留空（模板视觉不会变形，但缺空白）。

### figure-cheat-sheet.html — 速查卡（4 卡网格）

- **文件**：`figures/figure-cheat-sheet.html`
- **画布**：760 × 自适应
- **layout**：cheat-sheet-card
- **配色**：白底 `#ffffff` / 浅灰卡片 `#f8fafc`；4 卡顶 stripe 轮换 `#58a6ff / #3fb950 / #bc8cff / #FF8C42`
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 |
|---|---|---|---|
| FIGURE_CAPTION | R | 6-20 字 | 速查卡角色（如「Reviewer 检查表」） |
| FIGURE_TITLE | R | 6-18 字 | 速查主题（如「文章发布 · 7 项硬门」） |
| ITEM_{1..4}_TITLE | R | 4-12 字 | 每条规则的简短标题 |
| ITEM_{1..4}_BODY | R | 15-45 字 | 该规则正文 |
| ITEM_{1..4}_RULE | O | ≤30 字 | 该规则配套的 KO/法则（不填则隐藏；模板留有虚线分隔位） |

### figure-linear-progression.html — 线性进程（步骤 / 演化）

- **文件**：`figures/figure-linear-progression.html`
- **画布**：760 × 自适应
- **layout**：linear-progression
- **配色**：白底 `#ffffff` / 浅灰 step `#f8fafc`；4 步 accent `#2563eb / #059669 / #7c3aed / #ea580c`
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 |
|---|---|---|---|
| FIGURE_CAPTION | R | 6-20 字 | architect caption |
| FIGURE_TITLE | R | 6-22 字 | 过程主题 |
| STEP_{1..4}_LABEL | R | 2-8 字 | 阶段短标签 |
| STEP_{1..4}_TITLE | R | 4-12 字 | 阶段标题 |
| STEP_{1..4}_DESC | R | 15-45 字 | 阶段说明 |

### figure-binary-comparison.html — 二栏对比（错误 vs 正解 / 前后）

- **文件**：`figures/figure-binary-comparison.html`
- **画布**：760 × 自适应
- **layout**：binary-comparison
- **配色**：白底 `#ffffff` / 二栏浅灰 `#f8fafc`；left 红 `#ef4444` / right 绿 `#059669`
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 |
|---|---|---|---|
| FIGURE_CAPTION / FIGURE_TITLE | R | 6-22 字 | architect caption / purpose |
| LEFT_LABEL / RIGHT_LABEL | R | 2-8 字 | 对比两侧标签 |
| LEFT_TITLE / RIGHT_TITLE | R | 4-14 字 | 对比两侧标题 |
| LEFT_POINT_{1,2}_TITLE / RIGHT_POINT_{1,2}_TITLE | R | 4-12 字 | 分点标题 |
| LEFT_POINT_{1,2}_DESC / RIGHT_POINT_{1,2}_DESC | R | 12-36 字 | 分点说明 |
| BRIDGE_RULE | R | 15-45 字 | 两栏对比后的转化规则 |

### figure-hierarchical-layers.html — 层级堆栈（系统分层）

- **文件**：`figures/figure-hierarchical-layers.html`
- **画布**：760 × 自适应
- **layout**：hierarchical-layers
- **配色**：白底 `#ffffff` / 浅灰 layer `#f8fafc`；四层 accent `#2563eb / #059669 / #7c3aed / #ea580c`
- **占位符**：

| 名称 | 必/选 | 字数 | 来源 |
|---|---|---|---|
| FIGURE_CAPTION / FIGURE_TITLE | R | 6-22 字 | architect caption / purpose |
| LAYER_{1..4}_LABEL | R | 2-8 字 | L1/L2 或层级短名 |
| LAYER_{1..4}_TITLE | R | 4-14 字 | 层级标题 |
| LAYER_{1..4}_DESC | R | 12-36 字 | 层级机制说明 |
| LAYER_{1..4}_OUTPUT | R | 4-18 字 | 该层输出 / 影响 |

---

## 通用规则

1. **占位符 100% 填充**：required 项缺失 → `article_contract validate-visuals` 拒收。
2. **不允许出现裸 `{{...}}`**：检查产出 HTML 是否还残留任何 `{{[A-Z_]+}}` 模式。
3. **白底体系不可破坏**：V1-V10 与 figures 默认白底；可为特定文章新增 HTML 模板或微调 accent，但不得回到黑色/暗色背景系列。
4. **品牌 footer 永远保留**：V1-V8 默认保留 "DecoupleAI"（若 `account_id=studio` 则改为 "数据STUDIO"）；V9-V10 保留 "数据STUDIO"（不可互换）。
5. **账号隔离**：V9/V10 仅在 `account_id=studio` 时可选；V1-V8 在 `account_id=decoupleai` 时优先，在 `account_id=studio` 时可用但须切换品牌 footer。
6. **figures/ 输出边界**：figure HTML 只作为源码产物交付；不要同时为同一 `figure_id` 生成 SVG，能用 SVG V1 表达时优先 SVG。
