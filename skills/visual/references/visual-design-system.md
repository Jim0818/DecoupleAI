# Visual Design System — 视觉去AI味单一真相源

> **唯一真相源（C4）**：把本系统极强的**文字去AI味**护城河（`forbidden-words.yaml` + 《去AI味手册》）
> 延伸到**视觉**。借鉴《图解 Skill》`design-system.md` 的 9 节骨架（**借结构，不借它的赤陶三色品牌身份**）。
>
> **base + override 模式**（对齐 quality-gates 的 base + `platforms/{account}/quality-gates-override.yaml`）：
> 本文件 = 全账号共享的**反AI俗套硬规则 + Injection Block 模板 + 可读性自查门**；
> 各号差异化的「风格定位 / 调色板 / 元素」在 `platforms/{account}/platform_flavor.md` §视觉规范速查（已存在，本文件补强其上游骨架）。
>
> **消费方**：decouple-visual-designer（生成 `midjourney_prompts[]` / 出图 prompt 时，第 9 节 Injection Block **字面内联**每条 prompt）。

---

## 为什么要这层（北极星一致性）

图像模型**只读 prompt 字面**，看不到外部文件——所以视觉的「去AI味」约束必须**写进每条 prompt**，
不能像文字层那样靠 reviewer 事后查。这是和 `forbidden-words.yaml`（文字层）对称的视觉层防线。

---

## 9 节结构

### 1. 风格定位（一句话锚定 — 各号覆盖）
- decoupleai：工业理性，解剖室冷感（详见 platform_flavor §视觉规范速查）
- studio：代码工程冷峻，终端黑
- intellifuture：生活化暖意，未来微光
> 一句话定位写进 prompt 开头，给模型总基调。

### 2. 调色板（限定色数，变化靠透明度/灰度 — 各号覆盖）
- **硬约束**：单图主色 ≤3 个色相；层次变化靠**透明度 / 明度 / 灰度**，不靠加新色相。
- 各号具体 hex 见 `platforms/{account}/platform_flavor.md` §视觉规范速查 + visual-designer `persona-visual-specs.md`。

### 3. 对比硬规则（防暗底+暗字 — 必须字面写进每条 prompt）⛔
- 文字与背景对比度 ≥ WCAG AA 4.5:1（与 quality-checklist §A8 同源）。
- **严禁深色背景配深色文字 / 低饱和文字浮在杂底**。
- 封面中文标题字符高度 ≥ 画面短边 8%。
- **chat_image 封面风格限定**：印象派水墨风、无文字（仅画面中心的标题文字保留）。

### 4. 字体/字号层次
- 无衬线为主（思源黑 / 苹方）；标题 > 副标 > 正文 ≥ 3 级对比；克制衬线与手写体。

### 5. 角色/元素规则
- 人物：禁人脸特写（用剪影/侧身/局部）；禁品牌 logo。
- 主体物象取自 persona 隐喻库（structure 轴）+ layout 视觉语法（figure-layouts.md）。

### 6. 构图节奏
- 留白比例：极简卡 ≥40%，信息卡 ≥20%；主体占比明确，忌平均铺满。

### 7. 反 AI 俗套硬规则清单（视觉禁用清单 — 去AI味核心）⛔

> 与 `forbidden-words.yaml` 对称的**视觉版禁用清单**。每条都要进 Injection Block。

| # | 严禁 | 为什么是 AI 味 |
|---|---|---|
| 1 | 无意义彩色渐变背景（紫蓝粉糊一片） | 默认生图最典型俗套 |
| 2 | emoji / 卡通表情塞进信息图 | 廉价、稀释专业度 |
| 3 | 圆角卡片 + 左侧彩条 的「企业模板」套版 | Canva/PPT 模板感 |
| 4 | 3D 玻璃拟物 / 霓虹发光过度 | 2020 era AI 渲染腔 |
| 5 | 伪真实 UI 截图 / 假仪表盘 | 误导且经不起细看 |
| 6 | 品牌 logo / 名人脸 | 版权 + 俗套 |
| 7 | 死板正交直角连线满屏 | 机械、无信息层次 |
| 8 | 企业 PPT 风「商务握手 / 齿轮 / 灯泡」陈词图标 | 最高密度 AI 味 |
| 9 | 为填满画面而堆的装饰元素 | 违反「信息榨取」纪律 |
| 10 | 限定调色板之外的色相乱入 | 破坏账号视觉身份 |

### 8. 可读性自查清单（出图后逐条过，任一 No 重做）— 接 quality-gate
- [ ] 所有文字对比度达 AA？
- [ ] 标题一眼可读（不被装饰遮挡）？
- [ ] 无第 7 节任一俗套元素？
- [ ] 色相 ≤3、未越出账号调色板？
- [ ] 主体清晰、留白达标、非平均铺满？
> 结果写入 `visual-designer.output.self_check.visual_ai_cliche_pass`（quality-gate `VD_HARD_AI_CLICHE` 消费）。

### 9. Prompt Injection Block（字面注入每条出图 prompt）⛔

> visual-designer 生成每条 MJ / 出图 prompt 时，**原封不动**追加以下英文块（图像模型只读字面）：

```
[STYLE DISCIPLINE — must follow]
- max 3 hue families, vary by opacity/value not new hues
- text contrast >= WCAG AA 4.5:1, never dark-on-dark
- NO: rainbow gradient background, emoji, rounded-card+left-color-bar template,
  glossy 3D / excessive neon glow, fake UI screenshot, brand logo, celebrity face,
  rigid orthogonal wires everywhere, corporate-PPT cliché icons (handshake/gear/lightbulb),
  filler decoration
- clear subject, ample negative space, not evenly tiled
```

> 中文封面 prompt 同样追加（模型双语可读）。各号可在 platform_flavor 追加 1-2 条专属禁用（如 studio 加「暖底色」、intellifuture 加「代码/架构图风」）。

---

## 校验接线

| 机制 | 位置 |
|---|---|
| Injection Block 已内联每条 prompt | visual-designer execution-reference §Step 4；self_check.injection_block_applied |
| 可读性 / 反俗套自查 | quality-checklist §C8 → self_check.visual_ai_cliche_pass → gate `VD_HARD_AI_CLICHE` |
| 各号调色板/定位覆盖 | `platforms/{account}/platform_flavor.md` §视觉规范速查 |

## 10. 源码产出硬门

Visual Designer 的交付物以源码为准。PNG 截图由发布前人工流程处理，不再由 VD 自动生成或作为必需产物。

- HTML card：Write `.html`，不得为同一 `figure_id` 同时生成 SVG。
- Mermaid：Write `.mermaid`/`.mmd`，严格工程语义图保留 Mermaid 源码。
- SVG figure：先 Write `.spec.json`，再运行 `python3 scripts/render_svg_figure.py {input.spec.json} --svg-output {output.svg}`。Spec / SVG 必须同 stem 落在 `visual_output_dir`。
- MJ prompt：2 条 prompt 必须分别 Write 为 `.txt`。
- `visual-output.json.files_written[]` 必须列出所有源码、Spec、SVG 与 prompt 的绝对路径。
- 路径不存在、Spec/SVG 校验失败、占位符残留，均为阻断；禁止在输出中标注"待截图"后绕过源码契约。

## 11. SVG Figure 设计令牌（正式知识主图）

### 11.0 效果优先边界：本文件管 token，不管构图编排

本节仍是 SVG 正式知识图的颜色、字体、间距、圆角、安全禁用项和基础可读性的唯一真相源；但**成图质量不由 token 自动保证**。

为避免把 design-system 写成第二个 SVG 执行器，以下职责必须分离：

| 层级 | 负责什么 | 不负责什么 |
|---|---|---|
| `visual-design-system.md` | token、安全禁用项、源码硬门、可读性底线 | 不决定节点语义角色、不决定 layout plan、不写坐标 |
| `figure-layouts.md` | layout 命名、概念表达结构、renderer_status | 不生成 spec、不复制 token |
| `svg-figure-composer` capsule | layout plan、节点角色、密度预算、spec 生成、成图复检 | 不改 token、不手写 XML、不绕过 renderer |
| `scripts/render_svg_figure.py` | 确定性渲染与 SVG 文档校验 | 不做审美判断、不替代构图规划 |

**效果优先解释**：当 SVG renderer 可以合法输出，但结果出现主次不清、中文拥挤、元素平均铺满、路径不可追踪、layout 名实不一致时，必须重排或 fallback。禁止把“schema 通过”当作“视觉通过”。

本节是 SVG-first 正式知识图的唯一样式真相源。`scripts/render_svg_figure.py` 只读取下方
`SVG-FIGURE-TOKENS` 机读块；Visual Designer SKILL、Spec、Python 模板不得复制或私设另一套
颜色、字体、间距、圆角或最小字号。

### 11.1 SVG 路由定位

- 正式知识主图、核心机制图、架构分层图、决策树、误区纠正图：优先 `svg`，但必须先过 `svg-figure-composer` 的 layout plan 与视觉复检。
- 路线图、冰山、漏斗、循环、生态图等未稳定支持的 SVG 结构，按 `figure-layouts.md` 的 `renderer_status` 执行 fallback；不得为了“最小改动”强行产低质量 SVG。
- sequence / state / class / ER / UML、复杂工程关系或开发文档：保留 `mermaid`。
- 表格、参数清单、控制台、Dashboard、高文字密度卡片：保留 `html_card` / `ui-view`。
- 同一 `figure_id` 只允许一个 engine。能用 SVG V1 表达的 figure 不得改走 HTML；若因文字密度或 V1 不支持而改走 HTML，必须写 `fallback_reason`。

### 11.2 SVG 硬规则

- SVG 必须包含 `xmlns="http://www.w3.org/2000/svg"`、`role="img"`、`aria-labelledby`、`viewBox`、`<title>`、`<desc>`。
- 禁止 `<script>`、事件属性、`foreignObject`、外部 URL、远程字体、远程图片、base64 大图和不可控 HTML。
- 单节点正文默认 ≤3 行；超过则拆图或转 HTML，不通过缩小字号规避。
- SVG 文件必须以换行结尾，保留多行格式，便于 Git diff。
- 视觉判断仍由 VD `self_check` 承担；安全、结构、引用、边界与源码落盘由脚本校验。

### 11.3 SVG 失败预防矩阵

| 类别 | 预防机制 |
|---|---|
| 箭头/marker | `<marker>` 必须先在 `<defs>` 定义，所有连线用 `marker-end="url(#id)"`，禁止正文使用箭头字符代替 |
| 引用/defs | 所有 `url(#id)` 必须能解析到已定义 id，`<defs>` 必须早于首次引用，重复 id 阻断 |
| viewBox/尺寸 | 只接受 exact-case `viewBox`，独立 SVG 必须有 `xmlns`，rect/text/path 坐标不得越出画布 |
| 排版/对齐 | 渲染器统一计算节点中心、连线端点和安全边距；自由 `transform` 禁用，避免跨渲染器偏移 |
| 溢出/密度 | 节点正文行数受 Spec 限制；文字密度高时转 HTML/ui-view，不通过缩小字号硬塞 |
| 颜色残留 | Spec 不允许颜色字段；所有颜色、字体、间距只从下方 `SVG-FIGURE-TOKENS` 读取 |
| XML 合法性 | ElementTree 解析、特殊字符 escape、文件末尾换行、禁止 raw SVG/HTML 注入 |
| 路径缺陷 | 零长度 path 阻断；非 `<defs>` path 坐标必须在 viewBox 内 |
| CSS/浏览器差异 | 禁 `overflow`、`transform`、renderer-fragile CSS/property；不用 `foreignObject`、远程字体、`<textPath>` |
| 构图质量 | engine=svg 必须有 layout plan；节点角色、分组、路径关系和密度预算缺失时阻断 |
| layout 名实一致 | `decision_tree` 必须有条件分支，`before_after` 必须左右对照，`mechanism_explainer` 必须有中心机制；名实不符阻断 |
| 视觉复检 | schema 通过后仍需人工/Agent 复检主次、留白、中文可读性、edge spaghetti；失败则重排或 fallback |
| diff/review | renderer 输出多行 SVG；禁止一行压缩 SVG 作为正式产物 |

<!-- SVG-FIGURE-TOKENS:START -->
```yaml
svg_figure_tokens:
  version: 1
  canvas_presets:
    article-landscape:
      width: 1920
      height: 1080
    article-square:
      width: 1440
      height: 1440
    article-portrait:
      width: 1080
      height: 1440
  colors:
    surface: "#f7f8f5"
    surface_alt: "#ffffff"
    surface_panel: "#eef4f1"
    ink: "#18202a"
    muted: "#5c6673"
    faint: "#d8ded8"
    line: "#9aa9a6"
    accent_primary: "#2f6f91"
    accent_secondary: "#2f9d8a"
    accent_warm: "#b8793a"
    risk: "#b05a4a"
  typography:
    font_family: "PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, Source Han Sans SC, system-ui, sans-serif"
    title_size: 54
    desc_size: 26
    node_label_size: 34
    node_body_size: 25
    small_size: 21
    min_mobile_label_size: 28
    label_max_chars: 18
    body_line_max_chars: 18
  spacing:
    safe_margin_x: 120
    safe_margin_y: 92
    header_gap: 36
    node_gap: 30
    inner_pad_x: 34
    inner_pad_y: 24
    section_gap: 44
  components:
    node_radius: 18
    node_min_height: 112
    node_stroke_width: 2
    line_width: 3
    arrow_size: 14
    focus_stroke_width: 4
    shadow_opacity: 0.10
    max_hue_families: 3
```
<!-- SVG-FIGURE-TOKENS:END -->

### 11.4 SVG 成图质量自检门（接 Visual Designer self_check）

每张 SVG 正式知识图除通过 schema / XML / 安全校验外，还必须给出 `svg_visual_quality_check`：

- `layout_match`：图形结构是否真正符合 layout 语义。
- `hierarchy_clear`：读者是否能在 3 秒内看出主节点、次节点和结论。
- `path_traceable`：流程/树/因果边是否能顺着阅读，不出现无意义交叉。
- `density_safe`：中文正文是否保持移动端可读，不靠缩小字号硬塞。
- `negative_space_ok`：留白是否服务理解，而不是平均铺满画布。
- `fallback_needed`：若任一项失败，必须写明重排方案或 fallback 引擎。

`svg_visual_quality_check` 失败时，禁止以“renderer 已输出 SVG”为由通过 Visual Designer 阶段。
