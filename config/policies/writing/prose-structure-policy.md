# 正文可见结构政策（Prose Structure Policy）

> 适用于主管内容任务及 `v4_2_content_first` 兼容运行。主管装配从 `config/system/capabilities.json` 的 `content_defaults` 提供当前 `prose_policy_revision`；编辑旧稿时可在任务 metadata 明确继承其原 revision。旧状态缺少该字段时仍按 revision 1 回放。本文定义正文是否允许出现小标题；句间推进与具体表达动作仍由 `skills/natural-prose/SKILL.md` 执行。

## 1. 唯一语义判断

Revision 2 由主管或受委派的写作员工结合读者任务判断结构；兼容运行由 Chief Editor 提供 `prose_structure_class`：

- `continuous_editorial`：普通文章、叙事、复盘、分析、工具介绍和一般教程以连续段落推进。
- `hard_technical`：读者任务确需在多个技术认知层之间导航，例如机制、架构、代码/配置、实验或排障。它只是分节权限，不要求实际使用 H2。

出现代码、安装命令，篇幅较长，或题材是 AI、软件、模型、工具，均不能单独决定为 `hard_technical`。`sectioned_editorial` 仅供 revision 1 历史运行回放；revision 2 的编译器拒绝它。

## 2. 确定性派生

主管任务直接遵守选定的结构权限，无须生成旧 Writing Contract。以下机器字段只供兼容运行使用，由 `compile_v42_contracts.py` 按映射派生，不允许 Agent 自由填写：

| revision | prose_structure_class | body_h2_policy | narrative_subheading_policy |
|---|---|---|---|
| 1、2 | `continuous_editorial` | `forbidden` | `forbidden` |
| 1 | `sectioned_editorial` | `allowed` | `allowed` |
| 1、2 | `hard_technical` | `allowed` | `allowed` |

因此：

- `continuous_editorial` 正文 narrative H2 必须为 0；H3/H4、`PART 01`、编号章节、`写在最后`/`总结`、独立粗体短行等不得作为 H2 替身。
- `hard_technical` 允许 H2，但没有数量、篇幅或固定章节配额。使用正文 H2 时，最后一个 H2 必须恰为 `## 写在最后`，其下须有真正的收束段落；无 H2 时自然停止，不额外加标签。
- revision 2 的参考资料采用无标题链接列表或脚注，不把参考区标题算成正文的最后一节。
- revision 1 的 `sectioned_editorial` 继续按原契约允许 H2，不追溯适用新收尾规则。

## 3. 不等于“没有结构”

`continuous_editorial` 仍应有清晰的信息顺序，只是结构由段落与局部语义接力承担。内部 coverage map、Claim map、material unit map 可以存在，但不得自动翻译成公开小标题。`hard_technical` 也不能把每个内部 coverage item 机械变成一节；只在跨技术层导航确实降低理解成本时分节。

列表、表格、代码块、引用、图片等内容装置不因为本政策被禁止；它们是否出现只看是否降低理解成本。

## 4. 机器 Gate

主管路径在既有内容审阅中检查指定 revision 的结构权限，不增加固定编译或审核阶段。以下 Gate 描述仅适用于仍消费 Writing Contract 的 v4.2 兼容路径：

- `body_h2_policy=forbidden` 时，正文出现 Markdown H2 → blocking finding；
- `narrative_subheading_policy=forbidden` 时，以 H3-H6 或明确伪标题代偿 → blocking finding；
- `body_h2_policy=allowed` 时，H2 为零或有多个都不单独构成 finding；是否有用由 Reviewer 结合导航需要判断；
- revision 2 的 `hard_technical` 一旦使用 H2，最后一个正文 H2 的标题和非空收束由脚本校验；
- fenced code 中出现 `##` 等字面内容不参与检测；
- 发布元数据区不属于 narrative body，不参与正文标题检查。

Body Reviewer 将结构违约归入 `structure` finding；Refiner 只能在已有 finding 范围内移除、改写或重接标题，不得自行添加新分节。Body Recheck 确认结构违约没有回归。

## 5. Skill 系列与视觉锚点

Skill 文章的“测试方法、实战、发现、优缺点、评估、适用人群”等要求属于**语义覆盖**，不得通过要求固定 H2 名称来验收。

视觉插入锚点优先绑定 Claim 或 Material Unit（如 `after_claim:C3`、`after_material:MU-003`），不得依赖 `H2:3` 之类的标题序号。

## 6. 与其他文件的职责边界

- 本文：决定正文可见结构权限。
- `skills/natural-prose/SKILL.md`：决定连续正文如何自然推进、如何局部修复。
- `article-writing-contract.schema.json`：结构政策的机器契约字段。
- `scripts/compile_v42_contracts.py`：从语义分类确定性派生机器政策。
- `scripts/article_contract.py`：正文结构 Gate 的确定性执行器。

不要在 Agent Prompt、账号 Overlay 或旧活人感文档中复制另一套 H2 规则。
