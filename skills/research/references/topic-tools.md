# 选题工具

由主管或获派 research 任务按需调用。入口在项目根目录：

```bash
python scripts/topics.py <<'JSON'
{"op":"candidates","account_id":"intellifuture"}
JSON
```

每次一个 JSON 请求，stdout 为结果。必需来源失败、版本冲突或坏请求非零；部分
资讯失败保留各源健康状态。工具只提供资料、记录与确定性检查，选题判断由主管完成。

## 按需查阅规划资料

当前选题从用户目标、账号 L1/L2、读者问题与具体材料出发。
`config/system/topic-planning.json` 保存文件指针、明确知识库根和所选 catalog，
不定义另一份编辑政策。旧题库及旧战略已标为 `usage: historical_reference`、
`default: false`；这是保留的历史灵感资料，不是默认排期与权威范围。
环境中的 `TEXTPICOS_AI_WIKI_ROOT` / `AI_WIKI_ROOT` 优先于本机配置。
该配置含本机路径，按私有配置保存；复制到其他设备时明确修改根目录。

```json
{"op":"planning","account_id":"studio"}
```

未显式提供 `sources` 时，只选配置中默认启用的文件。当前三账号旧来源均不默认
启用，因此返回 `not_selected / not_read`、`available_sources` 与 `baseline_refs`，
不调用桥接。这不是“题库为空”或“没有好题”，主管应继续当前任务。
`strategy` 使用同样选择规则；不为完成选题而自动逐个读取可选文件。

确实需要回看旧资料时，从 `available_sources` 选择明确文件传给 `sources`，例如：

```json
{"op":"planning","account_id":"studio","sources":[{"scope":"vault","path":"选题库/数据STUDIO/02_数据STUDIO_读者任务型全域选题库_v1.0.md","format":"markdown"}],"query":"Agent","limit":8}
```

显式请求经当前 kb-bridge dispatcher 执行。返回稳定 ID、原始位置、SHA-256 和实际
读取/解析状态；`source_selection` 保留所选文件的用途，已登记历史来源不能通过
请求改写成现行政策。读取成功不代表编辑价值、当前事实或真实作者经历已经核实。
query 只是查找线索。使用外部来源时按实际任务提供 `run_id`；若提供运行身份，
必须真实存在。系统维护环境仍拒绝外部库访问，测试使用隔离项目资料。

## 按需取资讯和需求信号

`sources` 列出单点配置 `config/system/topic-sources.json`。优先选择与本题有关的少量来源：

```json
{"op":"fetch","source_ids":["opencode-releases","opencode-issues","v2ex-programmer"]}
```

支持 RSS、Atom、JSON Feed、GitHub Releases/Issues/Discussions；每源有条数、页数、
超时和字节预算。需要继续取页时，把该源返回的 `next_cursor` 放入下一请求的
`cursors: {"source-id": {...}}`。不自动扩大窗口、翻完全部历史或持续重试。

GitHub Discussions 从显式配置的 token 环境变量读取凭证；未配置时为 `auth_required`。
HTTP 429/限流、网络失败、坏响应、有效空列表、304 缓存命中各自表达。成功请求更新
增量状态；部分失败保留已取到的可选线索，但不推进旧增量状态。完全失败不会抹掉
先前内容。`cache` 只回放旧结果，不代表当前服务健康。
RSSHub 等可用通用 Feed 接入；试点来源默认停用，只在明确需要时显式选择。

发布时间、更新时间、采集时间和事件时间分别保留，未知为 null。问题帖和 Issue 是
观察到的问题；聚合摘要尚未核验原文。相同 URL 去重保留出处，转载数量不增加独立证据。

## 留下必要证据

选定线索成为正式立项依据时，将返回的 `evidence_selections` 保存到当前活动 run。
每条包括实际 `source_id/item_id/expected_item_sha256`，绑定选择时看到的版本：

```json
{"op":"save-evidence","run_id":"本次实际运行ID","items":[{"source_id":"opencode-releases","item_id":"实际返回的条目ID","expected_item_sha256":"实际返回的64位哈希"}]}
```

结果落在该 run 的 `evidence/topic-source-items.json`，并返回版本。覆盖已有快照
必须传当前 `expected_sha256`；请求应包含最终需要保留的完整选定集合。来源条目在
选择后更新时会报版本冲突，需重新阅读后选择，不能静默替换所选材料。它记录取回
的线索而非核验结论，仍为 `source_not_checked`。关键原文验证沿现有研究方法补齐。
缓存清理后，这份已选材料仍可消费；不为每条未采用线索生成永久文件。

## 候选、登记与反馈

单一候选索引为 `resources/catalogs/topic-candidates.json`。先 `candidates` 读取
当前 revision；新建或改角度使用稳定 key，不用可变标题作身份：

```json
{"op":"candidate-upsert","expected_revision":0,"request_id":"本次唯一请求ID","record":{"account_id":"intellifuture","key":"稳定任务标识","title":"工作标题","reader_task":"读者要完成的具体任务","rationale":"有材料支持的选题理由","evidence_refs":["本次持久证据引用"],"material_gaps":["尚待核验的部分"]}}
```

这是结构示例，revision 和引用必须替换为实际值。同一 request_id 重试不会重复新增；
同 ID 换内容或版本不符会失败，需重新读取当前对象再合并。`format: markdown` 可从
同一索引生成简报。只改标题保持原候选 ID，跨账号选择需要实质读者任务差异。

`registry` 读取配置或请求明确选定的 catalog，返回每行来源、原始状态与冲突。
它不打开文章，不根据文件新旧猜发布。`resolve-conflict` 只保存有明确依据的判断：
需要账号、slug、observed_fingerprint、status、reason、actor、evidence_kind 和
evidence_refs；具体字段以候选服务的参数校验为准。原表变化后旧解决记录变为 stale。

```json
{"op":"feedback","topic_id":"实际候选ID","expected_revision":1,"request_id":"本次唯一反馈ID","event":{"kind":"selected","actor":"supervisor","reason":"本次实际选择理由"}}
```

支持 selected、改角度、缺材料、重复、偏题、不做与制作反馈，使用服务返回的
结构化错误定位非法值。`used`、`source_review`、制作投入及制作结果需真实证据。
执行者是 supervisor、作者还是用户要准确记录，不能替用户制造采纳意见。
`source-summary` 从实际保存的候选和反馈汇总来源贡献；样本少或无反馈就保持未知。

选择候选不触发写作、软件账号试用、购买或发布。派写作任务时传选中的身份、版本、
读者任务与证据，不把完整候选库、所有热榜和历史运行塞进上下文。
