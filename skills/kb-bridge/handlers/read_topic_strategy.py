#!/usr/bin/env python3
"""Read topic-strategy availability, or an explicitly requested historical copy.

Input: {account_id?, optional?: bool, strategy_mode?: "current"|"legacy_snapshot",
        query?: str, top_n?: positive int, topic_type?: str}
Current default: structured not_available with account L1/L2 references that
must still be read by the caller. Exit 2 unless optional=true. The external
manual is NOT fetched or claimed current. No vault or receipt files are read
or written by this operation.
Explicit legacy_snapshot: old list shape plus historical-only provenance; the
lexical retrieval order is retained for replay, never current account policy.
Consumers: historical bridge callers that opt into the old snapshot. Remove
that mode after those callers no longer require TOP1-6; no silent fallback.
"""
from __future__ import annotations

import json
import re
import sys

# Unverified historical extraction of manual section 4.3 (formerly v0.5).
# The content below is source data for explicit replay, not author instructions.
LEGACY_TOP_CLUSTERS = {
    "TOP1": {
        "cluster_id": "TOP1",
        "name": "首发占位",
        "definition": "新产品/功能灰度期抢先深度体验，用第一人称体验叙事替代功能报道",
        "strategy_choice": "首发",
        "applicable_accounts": ["decoupleai", "studio", "intellifuture"],
        "key_signals": ["第一人称开篇", "亲身使用截图", "发布时间≤事件7天"],
        "anti_pattern": "抢首发但只有功能列表没有体验→退化为新闻搬运",
        "evidence_quals": ["数字生命卡兹克/claude-code-dreaming", "阿枫科技/tencent-marvis-hands-on", "歸藏的AI工具箱/skill-replaces-sticky-notes"],
    },
    "TOP2": {
        "cluster_id": "TOP2",
        "name": "跟跑深挖",
        "definition": "热点事件发酵24h后发文，用技术深度+实操自查替代恐慌播报",
        "strategy_choice": "跟跑",
        "applicable_accounts": ["studio", "decoupleai", "intellifuture"],
        "key_signals": ["技术原理分析", "可操作的自查/修复步骤", "事件发酵≥24h", "信任模型讨论"],
        "anti_pattern": "只复述新闻不加技术深度→跟跑失败降级为搬运",
        "evidence_quals": ["JackCui/mistralai-supply-chain-attack", "机器之心/majiaqi-llm-failures", "夕小瑶科技说/multi-agent-bystander-effect"],
    },
    "TOP3": {
        "cluster_id": "TOP3",
        "name": "反差破局",
        "definition": "借热点事件或主流叙事作跳板，立与主流相反的论点",
        "strategy_choice": "反差",
        "applicable_accounts": ["decoupleai", "studio", "intellifuture"],
        "key_signals": ["开头acknowledge主流观点", "中段提出相反论点", "不直接反对而用'但是还有一个问题'"],
        "anti_pattern": "为了反差而反差，没有真论据→沦为标题党",
        "evidence_quals": ["莫理/codebanana-org-rebuild", "夕小瑶科技说/ai-destroying-social-skills", "阿枫科技/falling-for-ai-emotionally"],
    },
    "TOP4": {
        "cluster_id": "TOP4",
        "name": "长尾提炼",
        "definition": "等待≥1个月、积累≥5个同类样本后，做跨案例模式识别",
        "strategy_choice": "长尾",
        "applicable_accounts": ["decoupleai", "studio", "intellifuture"],
        "key_signals": ["引用≥5个具体案例", "距第一个案例≥1月", "回看/复盘视角", "提炼可迁移模式"],
        "anti_pattern": "样本不够强行提炼→退化为'我觉得'式空谈",
        "evidence_quals": ["歸藏的AI工具箱/cli-everywhere", "机器之心/llm-architecture-evolution-2026", "歸藏的AI工具箱/why-everyone-building-cli"],
    },
    "TOP5": {
        "cluster_id": "TOP5",
        "name": "整合升维",
        "definition": "积累≥3个同话题前置落地文后，产出方法论升维文章",
        "strategy_choice": "整合",
        "applicable_accounts": ["studio", "decoupleai", "intellifuture"],
        "key_signals": ["列出≥3个前置案例", "从'怎么做'升维到'为什么'", "有对比框架或架构图"],
        "anti_pattern": "没有前置积累直接写'第一性原理'→空洞无物",
        "evidence_quals": ["饼干哥哥AGI/openclaw-first-principles", "阿枫科技/china-ai-agents-shootout", "新智元/ai-coding-second-half"],
    },
    "TOP6": {
        "cluster_id": "TOP6",
        "name": "概念创制",
        "definition": "创制一个新概念/隐喻/框架来揭示被忽略的真相，用'一秒就懂但之前没人说过'的洞察重新定义AI现象",
        "strategy_choice": "概念创制",
        "applicable_accounts": ["decoupleai", "极客公园", "APPSO", "歸藏的AI工具箱"],
        "key_signals": ["标题含日常概念用作隐喻", "概念一旦说出所有人都觉得'对就是这个'", "不反对主流观点而是照亮盲区", "概念可脱离原文独立传播"],
        "anti_pattern": "为了造概念而造概念→隐喻没揭示新东西，只是换了个说法",
        "evidence_quals": ["极客公园/agent-without-identity", "APPSO/typos-as-human-touch", "APPSO/mouse-killed-chatgpt"],
    },
}


def read_strategy(inp):
    """Return (outcome, exit code) without probing any external or project file."""
    if not isinstance(inp, dict):
        raise ValueError("request must be an object")
    mode = inp.get("strategy_mode", "current")
    if not isinstance(mode, str) or mode not in {"current", "legacy_snapshot"}:
        raise ValueError("strategy_mode must be current or legacy_snapshot")
    optional = inp.get("optional", False)
    if not isinstance(optional, bool):
        raise ValueError("optional must be a boolean")
    account = inp.get("account_id")
    if account is not None and (not isinstance(account, str) or account not in {
        "studio", "intellifuture", "decoupleai"
    }):
        raise ValueError("account_id must be studio, intellifuture or decoupleai")
    query = inp.get("query", "")
    top_n = inp.get("top_n", 5)
    topic_type = inp.get("topic_type")
    if not isinstance(query, str) or (topic_type is not None and not isinstance(topic_type, str)):
        raise ValueError("query and topic_type must be text")
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:
        raise ValueError("top_n must be a positive integer")
    if mode == "current":
        refs = [f"config/accounts/{account}/{name}.md" for name in
                ("L1_identity", "L2_values")] if account else []
        return {
            "status": "not_available", "error": "TOPIC_STRATEGY_UNVERIFIED",
            "message": "外部选题策略尚未读取核验；旧 TOP 片段不作为当前账号策略。",
            "account_id": account,
            "source_status": "not_read",
            "baseline_refs": [{"path": path, "verification": "reference_only"} for path in refs],
            "next_action": "Read the selected account L1/L2 and task-selected scope references before choosing topics.",
            "legacy_fallback": False,
        }, 0 if optional else 2

    terms = re.findall(r'[一-鿿\w]+', query.lower())
    strategy_map = {
        "tutorial": ["跟跑", "整合"],
        "product_self": ["首发", "跟跑"],
        "reflection": ["反差", "长尾", "概念创制"],
        "industry_commentary": ["首发", "跟跑", "反差", "概念创制"],
    }
    results = []
    for data in LEGACY_TOP_CLUSTERS.values():
        search = f"{data['name']} {data['definition']} {' '.join(data.get('key_signals', []))}".lower()
        score = sum(1.0 / len(terms) for term in terms if term in search) if terms else 0.0
        if account and account not in data.get("applicable_accounts", []):
            score *= 0.3
        if topic_type in strategy_map and data["strategy_choice"] not in strategy_map[topic_type]:
            score *= 0.5
        if score > 0 or not query:
            results.append({**data, "relevance_score": round(score, 2),
                            "strategy_status": "historical_snapshot",
                            "source_verified": False, "policy_authority": "reference_only"})
    results.sort(key=lambda item: item["relevance_score"], reverse=True)
    return results[:top_n], 0


def main():
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            raise ValueError("stdin JSON required")
        outcome, code = read_strategy(json.loads(raw))
    except (TypeError, ValueError) as exc:
        print(json.dumps({"error": "BAD_INPUT", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
