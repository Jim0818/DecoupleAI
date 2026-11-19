# SVG 构图与复检

仅在 [路由](routing.md) 已选择项目内 SVG renderer 时加载。架构关系优先当前 Archify 方法；SVG 是需要受控矢量图时的制作选项。方法属于视觉员工，不增加岗位或串行阶段。

## 当前事实源

| 内容 | 来源 |
|---|---|
| 布局语义与实际支持范围 | [figure-layouts.md](figure-layouts.md) |
| 颜色、字体、间距、安全和可读性 | [visual-design-system.md](visual-design-system.md) §11 |
| Spec 字段 | `config/contracts/content/svg-figure-spec.schema.json` |
| 确定性渲染与文档校验 | `textpicos.rendering.render_svg_figure` |
| 受众与账号定位 | `config/accounts/{account_id}/L1_identity.md` 和当前任务 |

不复制令牌，不私设另一套 Schema，不手写 XML 绕过渲染器。

## 从图意到 Spec

先明确图片在正文哪个位置帮助解释什么，哪些关系有材料依据。选择已实现布局；高文字密度内容用 HTML/表格，复杂结构按 routing 选择更合适工具。

构图时想清主信息、阅读顺序、节点角色、分组、必要关系和密度。把这些选择写入 Spec 支持的 `role`、`lane`、`level`、`cluster`、`priority` 等字段；不默认另交 layout_plan、检查报告或失败说明文件。保留对任务有用的 Spec 与实际成图即可。

每个节点只承担一个清楚的信息功能，每条边表达必要关系。遵守当前 Schema 与渲染器的节点和文字边界；文字拥挤时压缩、拆图或换工具，不缩小字号硬塞。不要把段落逐句拆成节点，不为填满画面增加装饰节点。

| 布局 | 构图必须表达 |
|---|---|
| `layer_stack` | 层间递进与主层，不是一排等权卡片 |
| `pipeline_flow` | 可追踪的输入、处理、输出和主路径 |
| `decision_tree` | 明确条件、分支与结果，每条分支可解释 |
| `mechanism_explainer` | 中心机制及组成、因果或约束关系 |
| `before_after` | 共享对比轴、真正变化点和两侧合理密度 |
| `comparison_matrix` | 少量对象与清楚维度；密集矩阵转表格/HTML |

Spec 只使用当前契约允许字段，不写颜色、字号、坐标、XML、外部资源或任意 style。用任务 staging 中的 `<figure_id>.spec.json` 作为输入。

## 实际渲染

在项目根运行：

```bash
PYTHONPATH=src python -m textpicos.rendering.render_svg_figure <figure_id>.spec.json --svg-output <figure_id>.svg
```

`--check-only` 在内存验证和渲染，不落成图；`--quality-report <path>` 仅在任务需要确定性指标时使用。其通过状态不能代替视觉验收。

渲染失败先修输入；若当前布局或工具不适合，按 routing 选择可用替代并在现有任务结果说明原因。不能临时手写 SVG 绕过边界。消费端需要 PNG 时实际导出并检查。

## 查看成图再交付

查看实际输出，检查布局名与内容是否相符、主次与阅读路径是否清楚、连线是否必要且可追踪、中文和图注是否可读、画面是否裁切或溢出。来源、语义和正文位置也要一致。

出现主次不清、平均铺满、中文拥挤、连线交叉混乱、结构和结论无关时，重排或更换合适工具。自动校验通过只证明机器约束通过；未看图不能宣称视觉验收。

提交真实图片、必要 Spec/可编辑源和正文插入位置，沿用任务结果记录未解决项；不要默认增加第二套过程产物。
