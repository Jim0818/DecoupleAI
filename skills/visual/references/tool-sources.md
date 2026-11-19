# 绘图能力来源与采用范围

核查日期：2026-11-19。仅选择或维护工具时读取，不加入每次写作的常驻上下文。使用作者仓库与工具官方文档；版本和调用方式以当前宿主实际安装为准。

| 来源 | 核实能力 | 本项目采用范围 |
|---|---|---|
| [tt-a1i/archify](https://github.com/tt-a1i/archify) | 将结构化候选生成独立 HTML，支持架构/流程/时序等图型及导出；自动校验和看图检查有区别 | 使用本机已装版本作为架构图首选，按 archify reference 在 staging 执行与导出 |
| [JimLiu/baoyu-article-illustrator](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-article-illustrator/SKILL.md) | 分析文章配图位置，以类型、风格、配色组织插图；优先运行时原生生图能力，最后插入正文 | 借鉴位置、目的、风格和实际生成闭环；不复制其所有确认轮次、独立中间文件或外部后端设置 |
| [coleam00/excalidraw-diagram-skill](https://github.com/coleam00/excalidraw-diagram-skill) | 可编辑 Excalidraw JSON，带 Python/Playwright 渲染和看图修正流程 | 项目已有可选工具；手绘关系图按需使用，不替代架构图默认路由 |
| [axtonliu/mermaid-visualizer](https://github.com/axtonliu/axton-obsidian-visual-skills/blob/main/mermaid-visualizer/SKILL.md) | 将文本组织成 Mermaid，提供图型、语法和布局约束 | 项目已有轻量回退能力；发布端不支持 Mermaid 时须实际导出 |
| [PyMuPDF 图片文档](https://pymupdf.readthedocs.io/en/latest/recipes-images.html) | PDF 内嵌图片提取与 page.get_pixmap 的区域渲染 | 论文原图完整性检查后截取 Figure，保留矢量线条与标签；具体位置先看页面 |
| [Playwright 截图文档](https://playwright.dev/docs/screenshots) | 页面、全页与指定元素截图 | 已有浏览器能力可用时忠实截取网页图块；不假定每个宿主都有已登录会话 |

## 采用决策

- 优先使用已暴露的原生生图工具；第三方 API 包和模型名称都不能代替真实能力探测。
- 使用用户已有 Archify，不重复安装第二份；项目当前的 Excalidraw、Mermaid 和 HTML/SVG 导出工具保留为按需能力。
- PDF 和网页原图获取使用确定性工具，不为截图再引入一个总控 Agent。
- 从外部方法吸收可用做法，不搬入与项目冲突的固定图数、源码即完成、所有图强制生成式绘制等规则。
- 本次只调研和接入现有能力；未自动安装上述候选或配置付费供应商。后续安装仍按用户任务与实际授权决定。
