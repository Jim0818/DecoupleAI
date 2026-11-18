# TextPicOS Writing Workflow v4.2（机器生成）

> 请勿手改本文件。来源：`workflows/governance/writing-profile-topologies.yaml` 与 `phase-catalog-v4_2.yaml`。
> 重新生成：`python3 scripts/render_workflow_docs.py`。

- Runtime：`v4_2_content_first`
- 入口：`V42_EVIDENCE`
- 终点：`V42_HR2`

## 正常路径

### lean

```text
V42_EVIDENCE → V42_EDITORIAL_BRIEF → V42_HR1 → V42_WRITER → V42_BODY_REVIEW → V42_PUBLIC_SURFACE → V42_SURFACE_VALIDATE → V42_METADATA_WRITE → V42_HR2
```

正常路径 LLM 位置上限：`5`；完整正文读取上限：`2`。

### standard

```text
V42_EVIDENCE → V42_EDITORIAL_BRIEF → V42_HR1 → V42_WRITER → V42_BODY_REVIEW → V42_PUBLIC_SURFACE → V42_VISUAL_DESIGNER → V42_TITLE_JUDGE → V42_SURFACE_VALIDATE → V42_METADATA_WRITE → V42_HR2
```

正常路径 LLM 位置上限：`7`；完整正文读取上限：`3`。

### flagship

```text
V42_EVIDENCE → V42_EDITORIAL_BRIEF → V42_HR1 → V42_WRITER → V42_BODY_REVIEW → V42_PUBLIC_SURFACE → V42_VISUAL_DESIGNER → V42_TITLE_JUDGE → V42_SURFACE_VALIDATE → V42_CE_GATE → V42_METADATA_WRITE → V42_HR2
```

正常路径 LLM 位置上限：`8`；完整正文读取上限：`3`。

## 条件节点

- `V42_AUTHOR_CONTEXT`：当 `author_context_required=true` 时激活。
- `V42_REFINER`：当 `refiner_required=true` 时激活。
- `V42_BODY_RECHECK`：当 `refiner_required=true` 时激活。
- `V42_VISUAL_DESIGNER`：当 `visual_required=true` 时激活。
- `V42_TITLE_JUDGE`：当 `title_judge_required=true` 时激活。
- `V42_CE_GATE`：当 `ce_gate_required=true` 时激活。

## Reviewer-first 修复路径

```text
V42_WRITER → V42_BODY_REVIEW
  ├─ none → V42_PUBLIC_SURFACE / V42_VISUAL_DESIGNER
  ├─ refiner → V42_REFINER → V42_BODY_RECHECK → public surfaces
  ├─ writer_rewrite → V42_WRITER
  └─ research → V42_EVIDENCE
```

## 路由

- `V42_HR1` + `REVISION` → `V42_EDITORIAL_BRIEF`；计数器 `architect_iter`。
- `V42_HR2` + `REVISION` → `V42_WRITER`；计数器 `revision_round`。
- `V42_BODY_REVIEW` + `REWRITE` → `V42_WRITER`；计数器 `revision_round`。
- `V42_BODY_REVIEW` + `RESEARCH` → `V42_EVIDENCE`；计数器 `reject_count`。
- `V42_BODY_RECHECK` + `REWRITE` → `V42_WRITER`；计数器 `revision_round`。
- `V42_BODY_RECHECK` + `RESEARCH` → `V42_EVIDENCE`；计数器 `reject_count`。
- `V42_SURFACE_VALIDATE` + `REGENERATE` → `V42_PUBLIC_SURFACE`；计数器 `revision_round`。
- `V42_SURFACE_VALIDATE` + `TITLE_ESCALATE` → `V42_TITLE_JUDGE`；计数器 `revision_round`。

## 不变量验证

```bash
python3 scripts/validate_profile_topology.py --all
python3 -m pytest scripts/engine/tests/test_v42_workflow.py tests/test_v42_topology.py -q
```
