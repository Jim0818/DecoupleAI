# Claim Evidence Policy

Claim handling follows C1: scripts validate structure, traceability, and required fields; Reviewer judges semantic sufficiency.

## Runtime Scope

Current supervisor tasks use the selected sources, author materials, and task instructions to establish what may be claimed. Preserve source identity, relevant dates and versions, and the evidence for consequential conclusions. A task does not need a Writing Contract, Claim Ledger, Author Input Bundle, or a phase report merely to write or review supported prose.

The named fields and schema examples below apply when a legacy run explicitly consumes those structured contracts. Their evidence principles also apply to supervisor tasks, using the task's actual materials and provenance rather than manufacturing old artifacts. An input label alone does not prove author experience or approval.

## Claim Ledger Scope

When a task uses a Claim Ledger, it records decision-driving claims, not every sentence.

Typical scope may be proportional to the production profile, but it is never a
minimum quota: `lean` often needs no more than 1-3 decision-driving claims,
`standard` often 3-5, and `flagship` often 3-7. Stop at the article's actual
claim count. A technical article may contain only `fact` and `inference` claims;
it never needs an `opinion` merely to fill the ledger.
- All claims used by title, TL;DR, conclusion, first-person judgment, and ecosystem-scale language.
- Claims containing “standard”, “turning point”, “leading”, “changed”, “first”, “core signal”, “lowered the threshold”, or equivalent high-strength wording.

Do not ledger:

- Ordinary background.
- Term definitions.
- Supporting details that do not affect the conclusion.
- Mechanism explanation, API shape, commands, configuration, parameters, and
  procedural steps when they are ordinary factual/detail support rather than a
  decision-driving claim. Their evidence boundary still applies.
- Pure reading-rhythm sentences.

Claim Ledger is a traceability index, not a second article outline. Writer and
Reviewer should consume a compact view containing only the claims used by the
current task or legacy phase; they do not need every upstream research field in prompt context.

## Claim Types

- `fact`: directly verifiable from a source.
- `inference`: engineering, product, or technical judgment derived from facts.
- `opinion`: author position or preference.
- `industry_claim`: ecosystem-scale claim about standards, turning points, competition, broad adoption, or category redefinition.

## Evidence Requirements

Every evidence item must be traceable. The following is the legacy structured form; current supervisor tasks preserve the relevant provenance in their selected material without requiring this schema:

```yaml
evidence:
  - id: E1
    source_type: official_repo
    source_ref: "https://example.com/repo"
    locator: "README > Training > Target Cache"
    evidence_grade: primary
    accessed_at: "2026-06-28"
    source_status: current
    official_self_report: true
    evidence_basis:
      type: official_documentation
      source_ref: "https://example.com/repo"
      locator: "README > Training > Target Cache"
      accessed_at: "2026-06-28"
      version_scope: "main branch at commit abc123"
      subject_scope: "OSS library"
      independently_reproduced: false
    measurement_basis: officially_reported
    version_scope: "main branch at commit abc123"
    conflict_notes: null
```

Allowed `evidence_grade` values:

- `primary`
- `secondary`
- `ecosystem`

Evidence for AI models, software products, repositories, benchmarks, standards, laws, schedules, and other volatile facts must include source freshness fields:

- `accessed_at`: date the source was checked.
- `source_status`: `current`, `stale`, `superseded`, or `unknown`.
- `official_self_report`: whether the source is an official or vendor self-report.
- `measurement_basis`: `not_numeric`, `measured_in_this_run`, `officially_reported`, `community_reported`, `estimated_from_docs`, `editorial_judgment`, or `unknown`.
- `version_scope`: version, release, commit, date range, or benchmark scope when relevant.
- `conflict_notes`: conflicting source note or `null`.

Missing freshness fields block v4 validation for volatile evidence. They are not replaced by prose disclaimers.

`evidence_basis.type` is the public wording authority:

| Type | Public wording allowed | Avoid |
|---|---|---|
| `verified_local_run` | “本文实测”“本次环境中”“运行后看到” | turning a local result into a universal guarantee |
| `official_documentation` | “官方示例”“文档中的最小调用方式”“该 API 的文档行为是” | “本文实测”“我跑通了” |
| `official_benchmark` | “官方 Benchmark 显示”“官方实测结果” | “本文实测排名”“真实通用成功率” |
| `official_maintainer_case` | “维护者记录过一个案例”“官方博客展示了” | “任何 Agent 都会自行修复” |
| `source_code_reading` | “源码显示”“当前实现中”“该版本包含” | “运行时一定会” |
| `third_party_test` | “第三方测试报告称” | “已被普遍证明” |
| `secondary_report` | “有报道提到” | decisive technical evidence |

Reliable first-party documentation can support natural technical prose. Do not force every sentence into “according to docs” disclaimers after a section/table/paragraph-level source disclosure. Hard failures are source or identity swaps: official materials written as the author’s local run, official benchmark written as this article’s benchmark, or component/version-specific evidence written as a product-wide guarantee.

Evidence permission is a ceiling on public wording, not a requirement to make
every paragraph sound like an audit report. Attribute once at the smallest
clear scope, then write naturally inside that scope until the source, subject,
version, measurement basis, or certainty changes.

Numeric tables and comparisons must expose measurement basis in the public
article when the source bases differ. Do not present measured data, official
self-reports, community reports, docs-based estimates, and editorial judgment
as one benchmark unless they were collected under the same task, model,
Harness, and context.

## Editorial Language Ladder

Use the lowest public language that still tells the truth.

| Evidence position | Public wording allowed | Public wording forbidden |
|---|---|---|
| Source only | "官方文档显示", "README 描述", "源码当前实现包含" | "本文实测", "我跑通了", "实际效果稳定" |
| Official benchmark | "官方 Benchmark 显示", "官方披露的测试结果" | "本文 Benchmark", "我们测出", "真实通用排名" |
| Verified local run | "本次环境中", "本文实测", "运行日志显示" | "所有环境", "任何网站", "产品已经稳定保证" |
| Maintainer case | "维护者案例里", "该案例说明" | "所有 Agent 都会", "该产品天然具备" |
| Static review | "静态审阅显示", "从仓库/文档看" | "完整测评", "长期使用后发现" |
| Editorial inference | "可以推断", "更合理的判断是", "在这个边界内" | "事实证明", "已经成为标准", "必然改写行业" |
| Unknown / pending | "仍需核查", "本文不判断" | any conclusion, ranking, or first-person scene |

The ladder controls titles, openings, body, metadata, visual captions, and
social copy. A higher-temperature account voice does not raise evidence
permission.

## Entity and Version Scope

Multi-object articles must keep claims within the entity and version their evidence supports. Current supervisor tasks make that scope clear in the selected material and wording. Legacy runs using a Writing Contract and Claim Ledger must define `entity_scope_map` and `claim_scope` for high-strength entries.

Separate at least:

- OSS library;
- CLI;
- Browser Harness / harness JS;
- Cloud product;
- official Benchmark;
- official docs / Quickstart;
- source-code version or commit.

Evidence does not transfer across entities by brand name. CLI direct-CDP behavior
does not prove the whole OSS library removed Playwright; Cloud stealth/CAPTCHA
behavior does not prove local OSS defaults; a maintainer case does not prove a
universal self-healing product capability.

Popularity numbers are dynamic background facts. Star count can support “high
attention” only with an accessed-at date; it cannot prove quality, market
leadership, community activity, “not hype”, or architecture innovation without
independent evidence.

## Headline and Metadata Alignment

The following outputs are claim-bearing public copy:

- title;
- subtitle;
- TL;DR;
- social post copy;
- SEO description;
- cover copy;
- metadata summary;
- conclusion.

Rules:

1. All public claim-bearing copy must obey the task's evidence and author boundaries. Legacy runs also obey their resolved Writing Contract and Claim Ledger.
2. A title or TL;DR must not elevate an `inference` into an `industry_claim`.
3. “标准”“转折点”“重新定义”“改写竞争逻辑”“全面领先” and equivalent wording require evidence and review at that scope; legacy structured claims use a reviewed `industry_claim`.
4. Social copy may simplify wording, but may not remove a key limitation when that limitation prevents overclaim.
5. Check the public surfaces actually requested against the body. Legacy Metadata Write validates its required title / TL;DR / social copy / SEO alignment; supervisor tasks do not add unused surfaces.

## Industry Claim Handling

When a legacy schema is in use, deterministic checks only verify structure:

- `industry_claim` has `evidence_ids`.
- Evidence entries include `source_type`, `source_ref`, `locator`, and `evidence_grade`.
- `industry_claim` has `reviewer_required=true`.
- Missing structural fields block validation.

The system must not silently relabel an `industry_claim` as an `inference` while leaving public wording unchanged.

Downgrade requires an explicit editorial action:

- revise the public wording;
- update the claim type;
- preserve a traceable revision record.

Whether evidence actually supports “standard”, “industry turning point”, or “competition rewrote” is a Reviewer semantic judgment, not a script decision.

## Reference Materials Section

When an article needs a public reference list, use a short source list instead
of an internal research report. This section is transparency, not narrative
closure, and is outside `ending_policy`.

```markdown
## 参考材料

- Source name — [domain.com](URL)
- GitHub repository (Star count as of YYYY-MM-DD) — [github.com/org/repo](URL)
- Paper — author / venue, year

> Boundary note: static review only / no local run / performance numbers from official benchmark.
```

Rules:

- Use the fixed heading `## 参考材料`.
- One source per line; put the link at the end.
- Star, release, pricing, benchmark, and version numbers need an as-of or
  accessed-at date when they affect the article.
- The final blockquote states verification boundaries; do not add a new H2 for
  "research boundary". Only `prose_structure_class=hard_technical` may use a visible H2 when that boundary is itself a genuine technical navigation layer.
- Never paste Source Consumption Report, Craft Review, local paths, run IDs, or
  internal artifact names into the public article.
