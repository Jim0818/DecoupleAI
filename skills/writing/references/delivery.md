# 文章交付

只在交付正式文章、处理文章元数据或准备明确请求的发布时使用。权威格式为 `config/contracts/content/article-output.schema.json`，实际校验与发布入口负责机器检查；写作按当前任务范围进行。

## 文章文件与元数据

已有文章先保留文件名、slug、run_id、account_id、date、column、tags、published_to 和其他有效字段。纯措辞修订只动指定正文；标题任务只修改标题及直接对应的公开文案。不要重生成整稿、重建 run 或擅自更换账号、栏目、发布时间。

新正式文章使用 schema 要求的 YAML frontmatter：`title`、`slug`、`run_id`、`account_id`、`column`、`date`、`tags`、`published_to`。run_id 来自实际运行，不能临时编造；账号与栏目来自当前任务及账号配置；未发生发布就不能填写已经发布的状态。tags 为字符串列表，published_to 保持消费端接受的字符串或字符串列表。

文件名遵守 `YYYY-MM-DD-slug.md`，按当前账号命名约定可使用 `_studio` 或 `_intellifuture` 后缀；slug 为小写英文/数字与单连字符。不要因标题润色自动改 slug 或文件名。字段缺失且无法从已授权输入可靠确定时，明确列出缺口。

## 正文与资源

正文只保留读者会读到的内容，开场白就是正文开头。保留代码、命令、引用、图片标记与原有可用链接；移动资源或重命名文件必须符合任务允许范围，并同步直接引用。不得用不存在的图片路径或生成提示词替代实际资源。

`visual_asset_paths` 与 H2 列表/长度由内容适配器从文章和已选资源提取，不在正文末尾塞入 JSON 契约或手写派生 H2 清单。每次应用 visual 方法，按实际能力生成原创插图、绘制结构图和取得来源图；保持源文件、导出文件和文章引用一致。无法取得的图按 visual/source-figures 约定在正文对应段落保留可见待补图块，草稿交付明确缺口，不能用空路径冒充已配图。

## 交付范围与发布授权

普通新稿直接形成当前任务所需的正式稿，不额外生成备选标题、营销栏目或发布包。文章校验读取当前正文、frontmatter 和实际引用资源。发布须有用户明确指令，写完文章不等于已经发布。

任务确为 Skill 系列时，按实际验证方式填写可选的 `skill_verification_mode` 并遵守真实核验边界。`measured_evaluation` 必须有实际运行证据；静态阅读、接口试验、情景演练与构建记录分别如实标记，不能为了获得通过提升证明强度。

## 当前运行的发布校验

发布按当前完成批次中的正式交付版本校验。正文以及被正文引用的图片必须已经作为本次运行交付，文件哈希和大小与完成记录一致；修订后须再次完成交付。--force 不能绕过这些条件。

发布适配器要求本地图片存放在 `articles/pending/visuals/<run_id>/`，并在正文使用有效相对引用。视觉员工先写 staging，主管通过运行时将所需图片晋升到该正式目录并登记为交付；不得仅把任意临时路径写进正文。发布时只复制正文实际引用的图片并改写对应链接，不复制整个中间报告目录，源图和未引用文件保留。完整新稿遵循 visual 的必用与实际出图要求；用户明确要求纯文字或局部修订时保留其范围。带可见待补图块的 draft 可审阅，final 发布前须补齐真实图像、替换提示并重新完成交付。

明确发布目标后使用 `PYTHONPATH=src python -m textpicos.content.publication --article <项目内正式稿> --target <明确发布路径>`；`--dry-run` 只验证，`--force` 仅用于已授权的目标覆盖，不能跳过运行完成和资源校验。

写作员工根据稿件性质选择结构，无需用户填写新表：普通情报使用 `continuous_editorial`；需要分节展开机制、工程过程或技术步骤时使用 `hard_technical`。结构选择依次读取当前 run.metadata.prose_structure_class、文章 frontmatter.prose_structure_class，未提供时按 continuous_editorial。draft 对结构问题给出警告；final 按当前政策检查：continuous_editorial 不使用叙事 H2/H3 或伪标题，hard_technical 有 H2 时末节为“写在最后”且有实质正文。修改结构选择也须在当前授权范围内。
