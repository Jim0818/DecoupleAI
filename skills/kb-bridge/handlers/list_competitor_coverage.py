#!/usr/bin/env python3
"""kb-bridge-list-competitor-coverage — check which competitor accounts covered a topic.

Input: {topic_keywords[], time_window_days?, limit?, group_by_cluster?}
Output: [{account, slug, publish_date, cluster, strategy, match_score}]

v1.0: 130-qual corpus support, title search, cluster+differentiation_angle in output.
"""
import json
import re
import sys
from datetime import date as date_cls, timedelta
from pathlib import Path

from common.lib import AI_WIKI_ROOT, read_stdin_json, emit, err

TOPIC_QUAL_GLOB = "exemplars/**/*-topic-qual.md"


def extract_frontmatter(text):
    """Parse YAML frontmatter without external dependency."""
    if not text.startswith("---"):
        return {}
    try:
        end = text.index("---", 3)
        fm_text = text[3:end].strip()
    except ValueError:
        return {}

    fm = {}
    current_parent = None  # track nested dict parent key
    current_key = None     # the top-level key being built
    current_list_key = None  # key whose value is a list being appended to
    for line in fm_text.splitlines():
        # Simple YAML parser: flat keys, inline simple values, nested dicts, lists
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())
        m = re.match(r'^(\w[\w_]*):\s*(.*)', stripped)
        if m:
            key = m.group(1)
            raw_val = m.group(2).strip().strip('"').strip("'")

            if raw_val in ("true", "false"):
                val = raw_val == "true"
            elif raw_val == "null" or raw_val == "":
                val = None
            elif raw_val.startswith("[") and raw_val.endswith("]"):
                inner = raw_val[1:-1]
                val = [v.strip().strip('"').strip("'") for v in inner.split(",") if v.strip()]
            elif re.match(r'^-?\d+$', raw_val):
                val = int(raw_val)
            elif re.match(r'^-?\d+\.\d+$', raw_val):
                val = float(raw_val)
            else:
                val = raw_val

            if indent == 0:
                # Top-level key
                fm[key] = val
                current_key = key
                current_parent = None
                current_list_key = key if val is None else None
            elif indent >= 2 and current_key:
                # Nested under current top-level key
                parent = fm.get(current_key)
                if parent is None or not isinstance(parent, dict):
                    parent = {}
                    fm[current_key] = parent
                parent[key] = val
                current_list_key = None  # named key wins over list append
        elif stripped.startswith("- "):
            item = stripped[2:].strip().strip('"').strip("'")
            # Figure out which list this belongs to
            if current_list_key:
                target = fm.get(current_list_key)
                if target is None:
                    target = []
                    fm[current_list_key] = target
                if isinstance(target, list):
                    target.append(item)

    # Flatten topic_metrics into top-level for easier access
    if "topic_metrics" in fm and isinstance(fm["topic_metrics"], dict):
        pass  # keep nested, access as fm["topic_metrics"]["differentiation_angle"]

    return fm


def extract_cluster(fm):
    """Extract TOP cluster from technique_ids. Works with both flat and nested."""
    tids = fm.get("topic_technique_ids", [])
    if isinstance(tids, str):
        tids = [tids]
    for tid in tids:
        m = re.match(r'TOP_T-A(\d)', str(tid))
        if m:
            return f"TOP{m.group(1)}"
    return None


def nested_get(fm, parent_key, child_key):
    """Get a value from a potentially nested dict structure."""
    parent = fm.get(parent_key, {})
    if isinstance(parent, dict):
        return parent.get(child_key)
    return None


def main():
    inp = read_stdin_json()
    keywords = inp.get("topic_keywords", inp.get("keywords", []))
    time_window_days = inp.get("time_window_days", inp.get("days", 30))
    limit = inp.get("limit", 20)
    group_by_cluster = inp.get("group_by_cluster", False)

    if not keywords:
        err("topic_keywords (or keywords) is required", code="BAD_INPUT")

    results = []
    today = date_cls.today()
    cutoff = today - timedelta(days=time_window_days)

    for qf in AI_WIKI_ROOT.glob(TOPIC_QUAL_GLOB):
        try:
            text = qf.read_text(encoding="utf-8")
        except Exception:
            continue

        fm = extract_frontmatter(text)
        slug = fm.get("slug", qf.stem.replace("-topic-qual", ""))
        account = fm.get("source_account", qf.parent.name)
        pub_date_str = str(fm.get("publish_date", ""))
        topic_metrics = fm.get("topic_metrics", {}) or {}

        angle = (nested_get(fm, "topic_metrics", "differentiation_angle")
                 or fm.get("differentiation_angle", ""))

        # tags can be at top level (hand-written quals) or nested under topic_metrics (batch quals)
        tags = fm.get("topic_domain_tags", []) or []
        if not tags:
            tm_tags = nested_get(fm, "topic_metrics", "topic_domain_tags") or []
            if tm_tags and isinstance(tm_tags, list):
                tags = tm_tags
        # Fallback: check top-level tags field (some quals use different key name)
        if not tags:
            top_tags = fm.get("tags", []) or []
            if isinstance(top_tags, list):
                tags = [t for t in top_tags if not t.startswith("topic-")]  # exclude topic-qual meta tags
        if isinstance(tags, str):
            tags = [tags]

        cluster = extract_cluster(fm)

        # Search surface: slug + account + tags + title (first heading) + body preview
        title_line = ""
        body_preview = ""
        fm_ended = False
        fm_dashes = 0
        for line in text.splitlines():
            if line.strip() == "---":
                fm_dashes += 1
                continue
            if fm_dashes < 2:
                continue
            fm_ended = True
            if line.startswith("# ") and title_line == "":
                title_line = line[2:].strip()
            elif line.strip() and not line.startswith("---"):
                body_preview += line + " "
                if len(body_preview) > 300:
                    break

        search_text = f"{slug} {title_line} {account} {' '.join(tags)} {body_preview[:200]}".lower()

        match_score = 0
        matched_keywords = []
        for kw in keywords:
            if kw.lower() in search_text:
                match_score += 1
                matched_keywords.append(kw)

        if match_score > 0:
            # Parse publish_date
            try:
                pub_date = date_cls.fromisoformat(pub_date_str) if pub_date_str else None
                in_window = pub_date and pub_date >= cutoff
            except (ValueError, TypeError):
                pub_date = None
                in_window = True

            # Use event_anchor_date for distance if available
            event_date_str = nested_get(fm, "topic_metrics", "event_anchor_date")
            if not event_date_str:
                event_date_str = fm.get("event_anchor_date", "")
            try:
                event_date = date_cls.fromisoformat(str(event_date_str)) if event_date_str else pub_date
            except (ValueError, TypeError):
                event_date = pub_date
            distance = (pub_date - event_date).days if (pub_date and event_date) else None

            results.append({
                "account": account,
                "slug": slug,
                "title": title_line or slug,
                "publish_date": pub_date_str,
                "in_time_window": in_window,
                "distance_days_from_event": distance,
                "cluster": cluster,
                "strategy": angle,
                "viral_score": fm.get("viral_score"),
                "match_score": match_score,
                "matched_keywords": matched_keywords,
                "topic_domain_tags": tags[:5],
            })

    # Deduplicate by (account, slug)
    seen = set()
    deduped = []
    for r in sorted(results, key=lambda x: x["match_score"], reverse=True):
        key = (r["account"], r["slug"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    # Summary stats
    from collections import Counter
    cluster_counts = Counter(r["cluster"] for r in deduped if r["cluster"])
    strategy_counts = Counter(r["strategy"] for r in deduped if r["strategy"])
    account_counts = Counter(r["account"] for r in deduped)
    in_window = sum(1 for r in deduped if r["in_time_window"])

    output = {
        "summary": {
            "total_matches": len(deduped),
            "matches_in_time_window": in_window,
            "time_window_days": time_window_days,
            "keywords": keywords,
        },
        "by_cluster": dict(cluster_counts.most_common()),
        "by_strategy": dict(strategy_counts.most_common()),
        "by_account": dict(account_counts.most_common(10)),
        "results": deduped[:limit],
    }

    if group_by_cluster:
        grouped = {}
        for r in deduped[:limit]:
            c = r["cluster"] or "unknown"
            grouped.setdefault(c, []).append(r)
        output["grouped_by_cluster"] = grouped

    emit(output)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
