# Visual Design System — 视觉去AI味单一真相源

> 本文件保存原创视觉的共用风格、可读性与 SVG 令牌。借鉴《图解 Skill》design-system 的组织结构，具体规则由 TextPicOS 当前任务与账号定位确定。
>
> 本文件提供共用视觉约束与提示块。账号受众、声音和视觉定位读取 `config/accounts/{account_id}/L1_identity.md` 及当前任务；原创风格可按需参考 [style-library.md](style-library.md)。
>
> **消费方**：主管、写作、审阅和视觉员工按 visual 方法的模式选读。原创生图执行者把实际适用约束写入工具调用，不能以提示词代替成图。

---

## 为什么要这层（北极星一致性）

图像模型**只读 prompt 字面**，看不到外部文件——所以视觉的「去AI味」约束必须**写进每条 prompt**，
实际生成时须传入适用约束，出图后由视觉执行者与审阅员工检查效果。

---

## 9 节结构

### 1. 风格定位（一句话锚定 — 各号覆盖）
- decoupleai：工业理性，具体范围以 `config/accounts/decoupleai/L1_identity.md` 与当前任务为准
- studio：代码工程冷峻，终端黑
- intellifuture：生活化暖意，未来微光
> 一句话定位写进 prompt 开头，给模型总基调。

### 2. 调色板（限定色数，变化靠透明度/灰度 — 各号覆盖）
- **硬约束**：单图主色 ≤3 个色相；层次变化靠**透明度 / 明度 / 灰度**，不靠加新色相。
- 账号定位来自 `config/accounts/{account_id}/L1_identity.md`；原创风格按任务选择，项目 SVG 的具体颜色只读取 §11 令牌。

### 3. 对比硬规则（防暗底+暗字 — 必须字面写进每条 prompt）⛔
- 文字与背景对比度 ≥ WCAG AA 4.5:1。
- **严禁深色背景配深色文字 / 低饱和文字浮在杂底**。
- 文字规格适用于有标签的解释图，不要求原创封面加字。
- **原创微信封面默认**：47:20，印象派水墨风，无文字、Logo 或人物；没有“中心标题例外”。导出后核对实际比例，不凭 prompt 宣称达标。

### 4. 字体/字号层次
- 无衬线为主（思源黑 / 苹方）；标题 > 副标 > 正文 ≥ 3 级对比；克制衬线与手写体。

### 5. 角色/元素规则
- 原创微信封面默认不含人物、文字或品牌 Logo。正文插图按任务需要选择主体，不虚构真实操作证据。
- 来源原图/截图保留必要文字、图例、坐标轴、作者信息与水印；不套用原创封面的去文字、去 Logo 或限色规则破坏证据。
- 主体物象应服务正文解释；需要选择美学或概念结构时分别参考 style-library.md 与 figure-layouts.md。

### 6. 构图节奏
- 留白比例：极简卡 ≥40%，信息卡 ≥20%；主体占比明确，忌平均铺满。

### 7. 反 AI 俗套硬规则清单（视觉禁用清单 — 去AI味核心）⛔

> 这些约束用于原创图；来源图与真实截图按证据保真要求处理。实际生成时把适用约束写入提示。

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

### 8. 可读性复检（查看实际成图后处理问题）
- [ ] 所有文字对比度达 AA？
- [ ] 标题一眼可读（不被装饰遮挡）？
- [ ] 无第 7 节任一俗套元素？
- [ ] 色相 ≤3、未越出账号调色板？
- [ ] 主体清晰、留白达标、非平均铺满？
> 问题和未解决项写入现有任务结果；实际复检不要求新增检查报告文件。

### 9. Prompt Injection Block（字面注入每条出图 prompt）⛔

> 原创生图执行者生成提示词时，传入以下适用约束（图像模型只读实际调用内容）：

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

> 中文原创封面同样传入适用约束。账号或本次用户有更具体的视觉要求时，合并到实际提示；不要改动来源图的必要标签或真实身份。

---

## 校验接线

| 机制 | 位置 |
|---|---|
| 原创生成约束 | visual 方法的 create/revise 与真实工具调用 |
| 可读性与图文一致性 | 视觉员工实际看图，审阅方法检查影响阅读的问题 |
| 账号定位与本次要求 | `config/accounts/{account_id}/L1_identity.md` 与当前任务 |

## 10. 实际图片与必要源码

当前交付规则只认 `skills/visual/SKILL.md` 与 `references/routing.md`。原创插图实际调用可用原生生图能力；架构图优先 Archify；论文与博客保留原图或忠实截图。源码、prompt 和自动校验通过都不能替代实际成图。

- 任务 staging 中保留必要源文件，并导出消费端需要的图片；同一图的源码与导出图属于同一成果。
- 使用现有 SVG renderer 时仍先写 Spec，再渲染 SVG，并保留必要 Spec；需要 PNG 就真实导出。
- 不固定输出两条 MJ 提示词，也不固定全部交付格式。生成时把本页相关风格要求写入真实调用提示。
- 图片无法取得时，按 source-figures reference 在正文对应段落留下具体待补图块；不造路径、不假称完成。补齐后才删除提示。
- 沿用当前任务结果记录工具、来源、位置和未解决项，不增加独立中间报告。

## 11. SVG Figure 设计令牌（正式知识主图）

### 11.0 效果优先边界：本文件管 token，不管构图编排

本节仍是 SVG 正式知识图的颜色、字体、间距、圆角、安全禁用项和基础可读性的唯一真相源；但**成图质量不由 token 自动保证**。

为避免把 design-system 写成第二个 SVG 执行器，以下职责必须分离：

| 层级 | 负责什么 | 不负责什么 |
|---|---|---|
| `visual-design-system.md` | token、安全禁用项、源码硬门、可读性底线 | 不决定节点语义角色、不决定 layout plan、不写坐标 |
| `figure-layouts.md` | layout 命名、概念表达结构、renderer_status | 不生成 spec、不复制 token |
| `svg-composition.md` | 构图选择、节点角色、密度、Spec 生成与成图复检 | 不改 token、不手写 XML、不绕过 renderer |
| `textpicos.rendering.render_svg_figure` | 确定性渲染与 SVG 文档校验 | 不做审美判断、不替代构图规划 |

**效果优先解释**：当 SVG renderer 可以合法输出，但结果出现主次不清、中文拥挤、元素平均铺满、路径不可追踪、layout 名实不一致时，必须重排或 fallback。禁止把“schema 通过”当作“视觉通过”。

本节是选择项目 SVG renderer 时的唯一样式真相源。`textpicos.rendering.render_svg_figure` 只读取下方
`SVG-FIGURE-TOKENS` 机读块；视觉方法、Spec、Python 模板不得复制或私设另一套
颜色、字体、间距、圆角或最小字号。

### 11.1 SVG 路由定位

- 架构图与正式结构关系按当前 routing 优先 Archify；选择现有 SVG renderer 作为适配方案或回退时，本节令牌与安全约束生效，并进行实际成图复检。
- 路线图、冰山、漏斗、循环、生态图等未稳定支持的 SVG 结构，按 `figure-layouts.md` 的 `renderer_status` 执行 fallback；不得为了“最小改动”强行产低质量 SVG。
- sequence / state / class / ER / UML 等结构关系优先检查 Archify 对应模式；Mermaid 保留为轻量草图、用户指定或能力不可用时的回退。
- 表格、参数清单、控制台、Dashboard、高文字密度卡片：保留 `html_card` / `ui-view`。
- 同一图选择一个合适制作引擎，保留必要源文件与消费端成图。需要回退时说明实际原因，不因为 SVG V1 支持某布局就强行覆盖用户指定的 Archify 或更适配的能力。

### 11.2 SVG 硬规则

- SVG 必须包含 `xmlns="http://www.w3.org/2000/svg"`、`role="img"`、`aria-labelledby`、`viewBox`、`<title>`、`<desc>`。
- 禁止 `<script>`、事件属性、`foreignObject`、外部 URL、远程字体、远程图片、base64 大图和不可控 HTML。
- 单节点正文默认 ≤3 行；超过则拆图或转 HTML，不通过缩小字号规避。
- SVG 文件必须以换行结尾，保留多行格式，便于 Git diff。
- 视觉员工和审阅员工承担实际成图判断；安全、结构、引用、边界与源码落盘由脚本校验。

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
| 构图质量 | engine=svg 先明确节点角色、分组、路径关系和密度，保留在 Spec 的适用字段中，不默认另交计划文件 |
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

### 11.4 SVG 成图复检

每张 SVG 正式知识图除通过 Schema / XML / 安全校验外，还需查看实际输出，核对以下方面；结果沿用当前任务记录，不要求新增字段或报告：

- `layout_match`：图形结构是否真正符合 layout 语义。
- `hierarchy_clear`：读者是否能在 3 秒内看出主节点、次节点和结论。
- `path_traceable`：流程/树/因果边是否能顺着阅读，不出现无意义交叉。
- `density_safe`：中文正文是否保持移动端可读，不靠缩小字号硬塞。
- `negative_space_ok`：留白是否服务理解，而不是平均铺满画布。
- `fallback_needed`：若任一项失败，必须写明重排方案或 fallback 引擎。

任一实质问题未解决时，不能以“renderer 已输出 SVG”为由宣称视觉验收通过。
