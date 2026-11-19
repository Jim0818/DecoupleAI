# TextPicOS 选题使用说明

本页说明如何使用现行选题能力。日常仍然向主管说明目标；主管按本次缺口调用规划、
来源、候选与反馈工具。下方命令供工程维护或需要检查原始结果时使用。

## 1. 从哪种任务开始

| 你手上的材料 | 可以直接这样说 | 主管应交付什么 |
|---|---|---|
| 已有明确题目 | “为智性未来判断这个题：第一次让 Agent 整理三份资料。先看范围、重复与材料缺口。” | 是否值得继续、具体读者任务、可支持的内容形态和待补材料 |
| 想按现行规划安排下一篇 | “从数据 STUDIO 现行题库选择下一篇 Python 基础题，结合已选成果登记检查重复。” | 带题库原始题号、来源版本和理由的候选；没有热点也可以成立 |
| 想寻找近期机会 | “查看 OpenCode、Codex 的官方更新和公开使用问题，为数据 STUDIO 找值得研究的任务题。” | 真实变化或问题线索、适合的角度、出处及核验缺口 |
| 想继续一个候选 | “继续候选 ID …，把角度改为首次上手，保留来源，说明还缺哪些实测。” | 更新同一候选，保留身份、版本和先前反馈 |

主管读取当前账号 L1/L2 和本次选中的范围资料。普通 Agent 上手教程可以独立成立，
无需额外加入源码拆解、行业判断或先修 Skill。实际试用需要真实执行材料；只有文档
时可以做有出处的说明或待执行教程，不能改写为作者亲测。

## 2. 配置与来源所有权

| 对象 | 当前入口 | 所有权 |
|---|---|---|
| 账号身份、读者与内容承诺 | `config/accounts/<account>/` | 项目当前账号配置；ai-as-me 保持同源入口 |
| 当前规划和预定选题 | `config/system/topic-planning.json` | 明确指向外部原文件，kb-bridge 只读，不复制可写政策 |
| 可选资讯与需求来源 | `config/system/topic-sources.json` | 来源 ID、URL 或仓库、调用预算、是否默认启用 |
| 可继续使用的候选与反馈 | `resources/catalogs/topic-candidates.json` | 一个索引，稳定 ID、版本、变更与反馈历史 |
| 已选来源证据 | 当前 run 的 `evidence/topic-source-items.json` | 持久的选中快照；与可清理的抓取缓存分开 |
| 成果登记观察与冲突 | 请求或配置明确选择的 `resources/catalogs/` 文件 | 保留每个原表、行位置和状态；不凭新旧猜发布 |

本机的 `topic-planning.json` 含明确的知识库根和三账号文件指针，属于私有配置。
换机器时明确设置该根，或使用环境变量 `TEXTPICOS_AI_WIKI_ROOT` / `AI_WIKI_ROOT`。
工具不猜历史绝对路径，不遍历整个知识库。外部资料里的旧角色名、比例或阶段术语
是待解释的源材料，不能覆盖当前用户要求、账号基线与主管架构。

默认来源可以通过 `enabled: false` 停用。RSSHub 和 Discussions 等选配源仅在有缺口
时明确选择；Discussions 使用配置指定的 token 环境变量，密钥不放入 JSON。缺少凭证
会返回 `auth_required`。没有常驻采集器、自动付费调用或自动排序服务。

## 3. 工程入口

在项目根目录、使用项目已有 Python 环境运行：

```bash
python scripts/topics.py <<'JSON'
{"op":"sources"}
JSON
```

每次输入一个 JSON 对象，stdout 返回 JSON。坏请求、版本冲突或必需来源失败非零
退出。多源部分失败时仍返回已取得的有效资料，同时保留每个来源的状态和错误。
来源返回内容只是线索，`source_not_checked` 不等于原文已经核验。

### 规划和战略

以下 `run_id` 必须换成实际存在的活动研究运行：

```json
{"op":"planning","account_id":"intellifuture","run_id":"实际运行ID","query":"Agent","limit":8}
```

```json
{"op":"strategy","account_id":"intellifuture","run_id":"实际运行ID","query":"任务","max_chars":6000}
```

这两个入口调用当前 kb-bridge dispatcher，读取明确文件。返回原题号、稳定身份、
来源位置、SHA-256 和读取／解析状态。没有读到、解析失败和没有匹配结果分别表达。
题库表格列数异常会失败，不把错位字段当作正确标题或状态。

`TEXTPICOS_MAINTENANCE_SCOPE=system` 禁止外部库访问，工程测试使用隔离 fixture。
实际规划读取属于另行授权的研究操作，不能通过修改保护规则让维护测试触及真实库。

### 获取线索

```json
{"op":"fetch","source_ids":["opencode-releases","opencode-issues","v2ex-programmer"]}
```

默认每源有条数、页数、时间与响应字节预算；实际值以配置为准。需要继续时，将返回
的 `next_cursor` 放入下一请求的 `cursors` 对象，键为来源 ID。调用不会自动翻完历史。

```json
{"op":"cache","source_ids":["opencode-releases"]}
```

`cache` 是旧快照，不能用来宣称来源当前可用。抓取完全失败保留旧内容；部分成功保存
本次可用条目，但不推进最后成功的增量 state。发布时间、更新时间、采集时间和事件
时间独立保留；今天采到旧文章不会自动变成今日事件。

### 保存选中的材料

从聚合条目的 `evidence_selections` 复制所需记录，原样传给 `items`：

```json
{"op":"save-evidence","run_id":"实际运行ID","items":[{"source_id":"opencode-releases","item_id":"实际条目ID","expected_item_sha256":"实际返回的64位哈希"}]}
```

保存结果包含证据路径与版本。已存在快照时，必须传目标的当前 `expected_sha256`，
并包含最终要保留的完整集合。若来源条目在选择后更新，条目版本比较会拒绝保存，
需读新版本后重新判断。这避免把“当时选的 A”静默保存成后来的 B。

证据落盘后，抓取缓存删除不影响已选材料。关键主张仍须按现行研究方法核验原文。

## 4. 候选、反馈和制作状态

先读取当前索引与 revision：

```json
{"op":"candidates","account_id":"intellifuture"}
```

想要可读简报可加 `"format":"markdown"`。首次索引未建立时 revision 为 0；之后每次
修改都传刚读取的 revision。相同账号和稳定 `key` 保持同一候选 ID，标题不是身份。
`request_id` 标识一次实际操作：相同请求重试不重复写入，换内容必须换请求 ID。

```json
{"op":"candidate-upsert","expected_revision":0,"request_id":"本次唯一操作ID","record":{"account_id":"intellifuture","key":"agent-first-document-task","title":"让 Agent 整理三份资料，怎样检查结果","reader_task":"完成一次资料整理并检查遗漏与出处","decision":"needs_research","evidence_refs":["实际持久证据引用"],"material_gaps":["尚无作者实际执行记录"]}}
```

这是字段示例，revision、引用和缺口都应替换成实际值。版本不符时重新读当前对象并
合并变更，不覆盖另一位执行者或用户的新修改。

| 反馈 `kind` | 含义 | 对候选的影响 |
|---|---|---|
| `selected` | 选择继续这个题 | `selected`，不等于已经写作或发布 |
| `angle_changed` | 记录改角度的原因 | 保留决策；具体角度用同 key 更新 |
| `materials_missing` / `needs_research` | 当前材料不足 | `needs_research` |
| `observe` | 暂时观察 | `observe` |
| `duplicate` / `off_scope` / `not_worth_it` / `rejected` | 重复、偏题或明确不做 | `rejected`，保留理由 |
| `used` | 某来源已实际被消费 | 需要真实证据和该候选的来源 ID |
| `source_review` | 来源贡献判断 | 需要证据、来源 ID，以及 `useful_topic`、`reduced_verification` 或 `no_increment` |
| `production_result` | 记录实际制作观察 | 需要证据；只有实际记录支持时才填 `effort_minutes` |

```json
{"op":"feedback","topic_id":"实际候选ID","expected_revision":1,"request_id":"本次唯一反馈ID","event":{"kind":"materials_missing","actor":"supervisor","reason":"题目成立，但尚缺本次任务的操作输出与失败记录"}}
```

`actor` 要准确区分 supervisor、用户、作者或实际执行者，不替用户制造采纳意见。
`source-summary` 从这些明确记录展示来源涉及的候选、使用与判断，不自动给来源打分
或开停服务。没有制作反馈意味着未知；累计的已记录分钟数不代表总投入已经测量。

## 5. 登记冲突怎么处理

```json
{"op":"registry","account_id":"decoupleai"}
```

返回每行观察与冲突，不读取文章目录。若两个原表对同一账号、slug 分别记为 pending
和 published，工具保留两者。只有明确的用户确认、发布回执或已核实公开 URL 等依据
可支持 `resolve-conflict`；需要提供当前 `observed_fingerprint`、理由、执行者与证据。
原表以后改变时，先前裁决显示为 `stale_resolution`，需重新核对。

## 6. 常见结果与下一步

| 结果 | 含义 | 下一步 |
|---|---|---|
| `empty` | 成功读取但没有有效或匹配条目 | 可以继续现行规划或用户给题 |
| `partial` | 有有效材料，也有明确失败或不完整部分 | 只消费返回的可用材料；保留失败说明 |
| `auth_required` | 所选接口需要凭证 | 具备授权凭证时配置；也可继续其他来源 |
| `rate_limited` / `unavailable` | 限流或访问失败 | 按返回信息决定稍后调用或换已配置来源 |
| `INVALID_TABLE` / `STALE_SOURCE` | 选中题库损坏或版本变化 | 定位原始文件与行；修复或重新读取后判断 |
| revision 或条目版本冲突 | 别的操作已改变对象 | 重新读取，保留新变更，合并后再提交 |

旧 `sync-topics.sh` 已停止向登记表追加题库摘要，避免同时存在两种候选写入路径。
需要查看规划使用 `planning`，需要保留候选使用 `candidate-upsert`，需要看成果状态
使用 `registry`。进一步的函数字段与机制见 `skills/research/references/topic-tools.md`。
