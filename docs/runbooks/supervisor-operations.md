# 主管运行操作

此页说明工程入口。日常用户直接用自然语言交代目标，不需要手工构造回执。

## 启动与派工

示例假设原稿已在 resources/inbox/source.md。Runtime 的文件引用须位于当前项目内；可用项目相对路径，绝对路径也须指向项目内文件。

~~~bash
bash scripts/run_pipeline.sh start demo-edit "只修改原稿开头" studio --source-draft-ref resources/inbox/source.md
python scripts/textpicos.py add-task demo-edit --id opening --role writer --mode edit --goal "只改开头，其他内容保持" --input resources/inbox/source.md --write workspace/runs/demo-edit/result.md --deliverable workspace/runs/demo-edit/result.md
python scripts/textpicos.py dispatch demo-edit opening
~~~

上游文件尚未产生时，也可先登记带 depends_on 和未来 input_refs 的下游任务。派发时程序检查依赖和输入；缺少必要输入会记录为 blocked。

dispatch 返回 handoff_path、staging_dir 和 execution_started=false。drive-next 按 --limit 为就绪任务准备同类交接，默认最多 4 个；它也不调用宿主。若批次返回 jobs 与 errors，先处理已返回的有效交接和具体失败，避免把整批误当作没有派发记录。

主管读取 handoff，用宿主真实子 Agent 工具执行其中 prompt。ATTEMPT_TOKEN 从 handoff 的 token 字段取得，HOST_EXECUTION_ID 使用宿主实际返回的执行标识：

~~~bash
python scripts/textpicos.py bind-host demo-edit opening --token "$ATTEMPT_TOKEN" --host-id "$HOST_EXECUTION_ID"
~~~

交接文件生成不等于模型已经调用。context 只装配引用，员工需要真正读取必要方法和所选输入。员工只写 staging；主管通过最小结果对象提交，可用标准输入减少额外回执文件：

~~~bash
python scripts/textpicos.py submit demo-edit opening --token "$ATTEMPT_TOKEN" --result - <<'JSON'
{"outputs":[{"staged_path":"result.md","target_path":"workspace/runs/demo-edit/result.md"}],"summary":"仅修改首段"}
JSON
~~~

token 关联本次任务尝试，不宣称独立身份认证。submit 比较派发时的输入与目标文件版本后晋升成果。

主管核对目标后执行 python scripts/textpicos.py finish demo-edit --completion "仅修改开头，其余内容已核对"。finish 要求本批次必要任务成功、声明的必要交付存在；已提交文件被外部改动，或必要任务消费的输入版本已过期时，完成操作会拒绝。根据当前版本调整并重做受影响工作，再完成同一 run。全部任务成功只表示 awaiting_completion，业务验收仍由主管负责。默认终点是交付，发布需用户明确要求。

## 继续修改

### 写作上下文与材料用途

未指定 `skill_ids`（或值为 `null`）时使用角色默认技能；显式 `[]` 表示只保留角色必需技能。Writer 与 Reviewer 默认加载共享 `natural-prose`，不需要在每次任务里重复列出。新主管运行的正文政策默认值来自 `config/system/capabilities.json` 的 `content_defaults.prose_policy_revision`；续改旧稿时，可在任务 `metadata.prose_policy_revision` 中显式保留其原政策。

任务 JSON 的 `input_refs` 可附 `purpose`、`selection_reason` 与必要的 `approval_ref`。常用用途为 `draft`（原稿）、`source`（事实来源）、`author_context`（作者材料）、`style_reference`（表达参考）和 `approved_edit`（带明确认可来路的改稿对照）；也允许其他有意义的用途。标签只帮助读取和判断，不自动证明作者亲历或用户认可。材料按需读取，目录不会自动展开。

~~~json
{
  "input_refs": [
    {"path":"resources/inbox/source.md","purpose":"draft"},
    {"path":"resources/inbox/reference.md","purpose":"style_reference","selection_reason":"参考其如何用具体操作推进解释"}
  ]
}
~~~

### 输入版本与局部续改

输入版本默认比较整个文件。只有本次任务确实不依赖标签和流程状态时，主管才在该输入上指定 `"version_scope":"article_content"`：此时比较 Markdown 正文及除 `tags`、`workflow_status` 之外的 frontmatter。标题、作者、日期、来源、正文政策和未知字段仍属于依赖。无法可靠解析时退回完整文件比较；目标文件提交始终使用完整文件版本，不能借内容投影覆盖他人的元数据修改。

~~~bash
python scripts/textpicos.py revise demo-edit --feedback "开头再口语一点，其他不动"
~~~

在同一 run 添加受影响的新任务。以当前成品作 input，精确声明要改的文件；目标文件继续使用原位置。
update-task 可调整尚未运行、失败或阻塞的当前批次任务，使用 --spec <JSON> 和 --reason 记录变化。运行中的任务先 cancel，再用新任务 ID 添加替代；已结束任务的业务内容使用新任务表达。
--write <路径> 表示精确文件范围，支持版本比较。目录范围须在任务 JSON 中显式声明，例如 {"allowed_write_roots":[{"path":"workspace/runs/demo-edit/figures","kind":"directory"}]}；它只允许新建后代文件。

## 状态与中断

status 区分 planning、ready、running、waiting_user、blocked、awaiting_completion、completed、cancelled。
没有 ready 不代表完成。需要用户决策时记录 waiting_user；持续没有进展时明确阻塞。

cancel、finish 或 revise 可能返回 cancel_requests。主管要调用宿主真实停止能力，再通过 resume --host-states <JSON> 报告实际状态。
host 状态 unknown 不会被猜成失败；completed 仍需收集并提交结果。禁止为“解卡”手工改 engine-state。
host-states JSON 是执行标识到实际状态的映射，例如 {"worker-123":"cancelled"}。尚未绑定执行标识的任务可用 task_id；已绑定时使用 host_id。resume 返回的 awaiting_hosts 会说明 collect_result、reconcile_host 或 cancel_host，主管继续完成这些宿主动作。

## 恢复与旧运行

同一 run 只有一个权威状态文件。存量 artifacts 运行继续旧入口，新运行使用 workspace/runs。
新建显式兼容运行使用 bash scripts/run_pipeline.sh --legacy start <新run_id> ...。已有 Engine 运行可用 python scripts/textpicos.py legacy resume <run_id> 或 legacy status <run_id>，shell 入口也会按其 engine-state 路由 status/resume。只有 workflow-state 的旧 assisted 运行继续用原 next/check/advance 等命令。start/init 会拒绝覆盖既存运行；同一 ID 同时出现新旧状态时先解决归属，不自动挑选一份。
旧阶段规则、schema 与岗位在 config/legacy、config/contracts/legacy、agents/legacy 和 src/textpicos/legacy。
不可为了迁移只搬走 state 文件而丢掉旧引用。

## 验证

~~~bash
export TEXTPICOS_MAINTENANCE_SCOPE=system
bash scripts/audit.sh --scope system
python -m pytest
~~~

system 审计校验当前配置、真实引用、单一来源与源代码语法，不扫描 articles、archive、resources、存量 run 或外部库。
维护环境变量也约束新 CLI 的显式输入、写范围、交付路径和任务调整；它只用于系统维护会话。普通内容生产可按授权选择项目内文章。
pytest 使用隔离样例，实际用户资料路径受保护。--legacy-full 是另外的广域操作，不能在 system 维护范围运行。
TEXTPICOS_PYTHON 可指定依赖齐全的解释器；当前已验证本机 python 环境。

### 写作效果检查

`python scripts/eval_skill.py --role writer --mode edit --account studio --input resources/inbox/source.md --goal "改善开头，保留技术细节" --json` 复用当前生产上下文装配。复杂任务可用 `--task <任务JSON路径>`。复现一次已准备的实际交接时使用 `--handoff <handoff.json路径>`，保留其 prompt、材料与 staging 边界。

这些入口只准备输入，返回 `execution_started=false`；`--validate-only` 只验证结构和资源。实际行为检查仍需主管调用真实宿主员工、收集结果并核对。评判要求在 `assessment` 中单独保存，不进入生成 prompt。历史 Agent 目录的旧工单仅用于规则检查，不能代表当前生产效果。维护测试使用隔离样例，不读取实际 `articles/`。

## 文件生命周期

成果仅保留实际消费者需要的版本和引用。成功提交会清理本次 staging；取消的在途任务须确认宿主停止后再清理，其他失败尝试与恢复数据按状态处理。workspace 不能整体当作缓存删除。
长期案例与索引在 resources。workspace/migrations 保存本次有限迁移基线和回执，供核验及回退，不进入内容任务上下文。

生命周期入口按状态处理显式选定的 run：

~~~bash
bash scripts/lifecycle.sh
bash scripts/lifecycle.sh demo-edit --dry-run
bash scripts/lifecycle.sh demo-edit --apply
~~~

默认只报告；没有 run_id 时不枚举运行目录。--apply 只在同一 run 锁内重试 Runtime 已登记的 cleanup_pending，不按目录年龄移动运行。旧 --days 自动归档已移除。

有 pending_commit、活动任务、未确认停止的宿主、被输入或成果引用的私有路径时，保留整 run 并报告原因。宿主停止事实仍由主管通过既有 resume --host-states 登记；lifecycle 不推断停止，也不顺带恢复成果提交。未知或旧运行保留，未登记归属的 workspace/tmp 也保持原样；此入口不扫描文章、资料库、archive 或未知 artifacts 内容。
