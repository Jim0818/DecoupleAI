#!/usr/bin/env python3
"""kb-bridge-read-title-patterns — read title pattern data for Hook Master / Title Judge.

Input: {account_id?, top_n?, head_accounts?, recent_titles_days?}
Output: {account_patterns, cross_account_tt_clusters, recent_head_titles}
"""
import json
import re
import sys
from pathlib import Path

from common.lib import AI_WIKI_ROOT, read_stdin_json, emit, err

PATTERNS_DIR = AI_WIKI_ROOT / "05_synthesis/title-patterns-library"

# TT cluster definitions (cross-account)
TT_CLUSTERS = {
    "TT1": {"id": "TT1", "name": "数字承诺", "definition": "标题含数字+量词，给出可量化预期", "pattern": r'\d+\s*(个|倍|次|年|天|篇|条|分钟|万|亿|%)'},
    "TT2": {"id": "TT2", "name": "反差悬念", "definition": "含转折词制造认知反差", "pattern": r'(但|越.*越|其实|其实是|没想到)'},
    "TT3": {"id": "TT3", "name": "时间锚", "definition": "用时间词制造紧迫感", "pattern": r'^(刚刚|今天|昨天|这周|突发|炸裂)'},
    "TT4": {"id": "TT4", "name": "自嘲降权", "definition": "自我贬低降低读者防御", "pattern": r'(我.*焦虑|踩坑|避坑|别再|我承认)'},
    "TT5": {"id": "TT5", "name": "反问悬念", "definition": "用问句制造好奇缺口", "pattern": r'[？?]|怎么|为什么|凭.*什么'},
    "TT6": {"id": "TT6", "name": "列举诱惑", "definition": "数字+列举词暗示内容丰富", "pattern": r'\d+\s*(个|大|种|条|步|招|款|项)'},
}


def main():
    inp = read_stdin_json()
    account_id = inp.get("account_id")
    medium = inp.get("medium", "wechat")
    trigger_type = inp.get("trigger_type")
    top_n = inp.get("top_n", 5)
    head_accounts = inp.get("head_accounts", True)
    recent_titles_days = inp.get("recent_titles_days", 30)

    if medium not in {"wechat", "douyin"}:
        err("medium must be wechat or douyin", code="INVALID_MEDIUM")

    if medium == "douyin":
        video_dir = PATTERNS_DIR / "douyin"
        files = sorted(video_dir.glob(f"{trigger_type}-*.md")) if trigger_type else sorted(video_dir.glob("VH*.md"))
        templates = []
        for path in files:
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(
                r"###\s+(VH\d+-\d+).*?\n-\s+\*\*模板\*\*：`([^`]+)`",
                text,
                re.DOTALL,
            ):
                templates.append({
                    "id": match.group(1),
                    "template": match.group(2),
                    "trigger_type": path.stem.split("-", 1)[0],
                    "source": str(path.relative_to(AI_WIKI_ROOT)),
                })
        emit({
            "medium": "douyin",
            "trigger_type": trigger_type,
            "templates": templates[:top_n],
            "source_dir": str(video_dir.relative_to(AI_WIKI_ROOT)),
        })

    # Load account-specific patterns if account_id provided
    account_patterns = None
    if account_id:
        pattern_file = PATTERNS_DIR / f"{account_id}.md"
        if pattern_file.exists():
            text = pattern_file.read_text(encoding="utf-8")
            account_patterns = {
                "account": account_id,
                "file": str(pattern_file.relative_to(AI_WIKI_ROOT)),
                "has_data": True,
            }
            # Try to parse frontmatter for stats
            if text.startswith("---"):
                try:
                    import yaml
                    fm = yaml.safe_load(text.split("---")[1])
                    account_patterns["pattern_stats"] = fm.get("pattern_stats", {})
                    account_patterns["title_cluster_distribution"] = fm.get("title_cluster_distribution", {})
                    account_patterns["total_titles"] = fm.get("total_titles", 0)
                except Exception:
                    account_patterns["pattern_stats"] = {}
        else:
            account_patterns = {
                "account": account_id,
                "has_data": False,
                "message": f"No pattern file found for {account_id}",
            }

    # Collect cross-account TT cluster summary
    cross_account_tt = []
    if head_accounts:
        for tt_id, tt_data in TT_CLUSTERS.items():
            cross_account_tt.append({
                "cluster_id": tt_id,
                "name": tt_data["name"],
                "definition": tt_data["definition"],
            })

    # Collect recent head titles (from all available pattern files, for KO9 plagiarism check)
    recent_head_titles = []
    if PATTERNS_DIR.exists():
        for pf in sorted(PATTERNS_DIR.glob("*.md")):
            text = pf.read_text(encoding="utf-8")
            # Extract titles from numbered list
            title_matches = re.findall(r'^\d+\.\s+(.+?)$', text, re.MULTILINE)
            account_name = pf.stem
            for t in title_matches[:top_n]:
                recent_head_titles.append({
                    "account": account_name,
                    "title": t.strip(),
                })

    result = {
        "medium": "wechat",
        "account_patterns": account_patterns,
        "cross_account_tt_clusters": cross_account_tt[:top_n],
        "recent_head_titles": recent_head_titles[:top_n * 3],  # Cap for output size
    }

    emit(result)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
