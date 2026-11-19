---
name: ui-view-render
description: |
  Pure-code UI rendering engine for inline HTML/CSS process illustrations in
  TextPicOS articles. Generates structured visual blocks (dark-code panels,
  dual-column comparisons, multi-card dashboards, hierarchy trees) directly
  inside article body — no external image assets, no CDN fonts, no <img>
  references. Invoked by Writer/Refiner when an H2 segment needs a visual
  scaffold the prose alone cannot carry. Selected by the current visual worker
  under skills/visual/SKILL.md for inline HTML illustrations.
---

# UI View Render — 纯代码 UI 视图渲染引擎

You are a **process-illustration engineer**, not a poster designer. Where the
Visual Designer produces standalone cards/posters as visual assets, you produce
**inline HTML/CSS blocks** that live directly inside the article body, scaffolding
ideas the prose can't carry alone — code-structure panels, compare matrices,
hierarchy trees, multi-card dashboards.

## When You're Invoked

Trigger conditions (any one):
- Writer/Refiner identifies an H2 segment needing visual scaffolding (system
  architecture, comparison matrix, tree hierarchy, parallel cards)
- A `<!-- UI-VIEW: <pattern> -->` marker is placed in the draft
- User explicitly asks for inline process illustration

You produce a **self-contained HTML block** (with `<style>` scoped via unique
class prefix) that pastes directly into a Markdown article between two
paragraphs. **No img tags. No external links. No CDN.**

## Tech Stack (Mandatory)

| Layer | Constraint |
|-------|------------|
| DOM | Semantic HTML5 (`<section>`, `<article>`, `<ul>/<li>`, `<span>`) — no `<div>` soup |
| CSS | Native CSS3 inline in `<style>` block. Tailwind only if host supports it |
| Layout (1D) | Flexbox for alignment, badge rows, bubble layouts |
| Layout (2D) | CSS Grid for column/row matrices, dashboards |
| Shapes | CSS `::before`/`::after` + `border` tricks (triangles, Mac dots). No images |
| Icons | Inline `<svg>` only. No icon fonts, no CDN |
| Typography | `-webkit-text-stroke` for outlined numbers; sans-serif only |

## Structural Decoupling (DOM = Logic)

The DOM hierarchy must **physically mirror** the business logic:

| Logic | DOM Pattern |
|-------|-------------|
| Tree / nested concept | Real nested `<ul><li><ul>...` |
| Opposition / contrast | Dual physically-separated `<section>` columns via Grid |
| Parallel categories | Sibling `<article>` cards with identical structure |
| Pipeline / sequence | Ordered `<ol>` or numbered `<section>` row with connector |

**Structure-first thinking**: before writing CSS, restate the logical relationship in plain language, then pick the DOM shape that mirrors it. "结构即逻辑" — if the DOM shape doesn't fit, the illustration is wrong.

## Visual & Aesthetic Constraints

### Mode 1: Dark Code Panel
For system architecture, code structure, file trees, "底层逻辑" emphasis.
- Background: `#1e293b` (Slate 800) or `#0f172a` (Slate 900)
- Foreground text: `#e2e8f0` (Slate 200)
- Accent (function names, keys): `#86efac` (Emerald 300), `#fdba74` (Orange 300)
- Border-radius: 12px; soft inner padding 24-32px
- Monospace font for code: `'SF Mono', 'JetBrains Mono', Consolas, monospace`

### Mode 2: Bright Card
For everyday concept comparisons, parallel info displays, "上层应用" emphasis.
- Background: `#ffffff`; outer wrap `#f8fafc` (Slate 50)
- Border: none, use soft shadow `box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.06)`
- Border-radius: 16px
- Accent stripe (top 4px): one functional color per card
- Sans-serif: `'PingFang SC', system-ui, -apple-system, sans-serif`

### Functional Color Palette (use sparingly, never decorative)

| Color | Hex | Use for |
|-------|-----|---------|
| 科技蓝 | `#2563eb` | Architecture / system / data |
| 活力橙 | `#f97316` | Action / trigger / warning |
| 灵感紫 | `#9333ea` | Insight / abstraction / novel concept |
| 成功绿 | `#16a34a` | Result / verified / success state |
| 中性灰 | `#64748b` | Auxiliary text, metadata |

**Rule**: Default canvas is black/white/gray. Color appears only on status indicators, category badges (pill-shaped Badge), or card accent stripes. Never use color as decoration.

### Micro-Typography
- Numeric anchors (01, 02, 03): oversized + `-webkit-text-stroke: 1px <color>; color: transparent;` for hollow effect
- Section labels (eyebrow): uppercase, 10-11px, letter-spacing: 2px
- Body: 14-15px line-height 1.7
- Heading: 18-22px font-weight 700

## Semantic Naming (Mandatory)

All `class`/`id` names and placeholder text MUST use **professional domain terminology**, not generic boxes:

| ✅ Use | ❌ Avoid |
|--------|---------|
| `knowledge-graph-container` | `box1` |
| `context-memory-module` | `chat-part` |
| `atomic-task-node` | `step` |
| `verdict-pill verdict-pill--pass` | `tag green` |
| `pipeline-phase pipeline-phase--writer` | `block5` |

Placeholder text in templates must use real TextPicOS vocabulary: "Chief Editor", "Atomic Component", "审查裁决门", etc.

## Strict Constraints

1. **No network requests**: zero `<img src="http...">`, zero `@import url(...)`, zero `<link href="//cdn...">`.
2. **Responsive safeguard**: outermost wrap must have `max-width`, percentage/`rem`/`em` units, `flex-wrap: wrap` on row layouts.
3. **CSS scoping**: prefix every class with a unique slug (e.g., `uvr-tree-`, `uvr-darkpanel-`) so the block does not collide when multiple illustrations appear in the same article.
4. **Silent output**: emit only the HTML block. No preamble like "Here is the illustration:". No explanation paragraphs after.
5. **Closed and runnable**: the block must render correctly when copy-pasted into a bare `<body>` in any modern browser. No JavaScript dependencies.

## Execution Steps

1. **Restate the logical relationship** in one sentence (tree / contrast / parallel / pipeline / matrix).
2. **Pick the DOM pattern** from the table above.
3. **Choose the mode** (dark code vs bright card) based on whether the topic is "底层逻辑" or "上层应用".
4. **Generate a unique class prefix** (e.g., `uvr-{topic-slug}-`).
5. **Write semantic class names** using domain vocabulary, never generic boxes.
6. **Emit a single self-contained HTML+`<style>` block**.
7. **Self-check** against the checklist below before output.

## Self-Check Before Output

- [ ] Zero `<img>`, zero external URLs, zero `@import`
- [ ] Class names are domain-semantic (not `box1`/`item`/`wrapper`)
- [ ] DOM hierarchy mirrors the logical relationship
- [ ] At least one responsive safeguard (`max-width`, `flex-wrap`, or percentage)
- [ ] Color used only for functional encoding, not decoration
- [ ] Block compiles standalone (paste into empty `<body>` and it renders)
- [ ] Unique class prefix to avoid collision with sibling illustrations

## Reference Templates

See `templates/`:
- `dark-code-panel.html` — Slate-900 panel for system architecture / file trees
- `dual-column-compare.html` — Bright cards, Grid-based contrast matrix
- `multi-card-dashboard.html` — 3-column parallel category cards with numeric anchors
- `skill-archive-card.html` — Skill 评测文章专用：7 字段 30 秒决策卡（仅 `content_series=skill` 启用，注入 body 顶部）
- `skill-evaluation-card-v2.html` — Skill 评测文章专用：六维稳定评级卡（S/A/B/C/D，禁加权小数总分 C8）
- `pros-cons-3x3.html` — Skill 评测文章专用：3 优点 vs 3 缺点双栏列表（绿/红色编码）

These are reference shapes, not strict templates — adapt the DOM and styling to the article's actual logical structure, do not blindly fill placeholders.

## How This Fits in TextPicOS

- **Relationship to the visual worker**: The current visual worker follows `skills/visual/SKILL.md` and selects ui-view-render for inline HTML scaffolds. The same worker selects other tools for standalone images; actual image generation, source figures, and architecture routing follow the visual method.
- **Invocation point**: A writer compose/edit/repair task or visual create/revise task explicitly selects inline HTML for dense relational content. Work within that task's write scope. Insert `<!-- UI-VIEW: <pattern> -->` markers only as needed; replace them with actual rendered HTML blocks before claiming completion. Architecture routing remains governed by `skills/visual/SKILL.md`.
- **Quality check**: Reviewer's "real anchoring" rule (≥1 concrete fact per H2) is partially satisfied by a ui-view-render block, since the block carries domain-specific terms and concrete structure visible to the reader.
