#!/usr/bin/env python3
"""Historical scoring replay only; current discovery uses fetch.py.

Invoke this file explicitly only to reproduce an old ranked artifact. It keeps
its original arithmetic and result fields for the existing test/legacy reader;
its scores are not current editorial policy or input to research/discover.
Use --raw, --scored, --config and --out with the original saved inputs. Remove
this compatibility executable only when saved-run readers and test_score.py no
longer need that format. config.json keeps these values under legacy_scoring.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def aggregate(score: dict[str, float], weights: dict[str, float]) -> float:
    return sum(weights[d] * score[d] for d in weights) * 10.0


def apply_rules(score: dict[str, float], evidence: dict[str, str],
                rules: list[dict], dimensions: list[str]) -> tuple[bool, float, list[str]]:
    """
    Returns (keep, delta_total, rule_trace). `keep=False` means filtered out.
    """
    delta = 0.0
    trace: list[str] = []

    spread = max(score.values()) - min(score.values())

    for rule in rules:
        rid = rule["id"]
        action = rule["action"]

        # Hand-rolled conditions; safer than eval(when) on user-edited YAML.
        if rid == "filter_low_signal":
            cond = score.get("signal_strength", 0) <= 2
        elif rid == "filter_low_factuality":
            cond = score.get("factuality", 0) <= 2
        elif rid == "demote_unsupported_high_dim":
            cond = any(score.get(d, 0) >= 8 and not (evidence.get(d) or "").strip()
                       for d in dimensions)
        elif rid == "promote_novel_deep":
            cond = score.get("novelty", 0) >= 8 and score.get("technical_depth", 0) >= 7
        elif rid == "promote_broad_impact_factual":
            cond = score.get("impact_scope", 0) >= 8 and score.get("factuality", 0) >= 7
        elif rid == "demote_score_collapse":
            cond = spread <= 1
        else:
            # Unknown rule id — refuse rather than silently skip.
            raise ValueError(f"Unknown rule id in config: {rid}")

        if not cond:
            continue

        if action == "filter":
            trace.append(f"FILTER:{rid} ({rule.get('note', '')})")
            return False, 0.0, trace
        elif action == "demote":
            delta += rule["delta"]
            trace.append(f"DEMOTE:{rid} {rule['delta']}")
        elif action == "promote":
            delta += rule["delta"]
            trace.append(f"PROMOTE:{rid} +{rule['delta']}")
        else:
            raise ValueError(f"Unknown action: {action}")

    return True, delta, trace


def time_decay(base: float, hours: float, lam: float) -> float:
    return base * math.exp(-lam * hours)


def hours_since(iso: str, now: datetime) -> float:
    # Accept both Z-suffixed and offset-bearing ISO 8601.
    s = iso.rstrip("Z")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt).total_seconds() / 3600.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, type=Path)
    ap.add_argument("--scored", required=True, type=Path)
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--now", default=None, help="ISO timestamp, defaults to now (testing hook)")
    args = ap.parse_args()

    cfg = load_json(args.config)
    cfg = cfg.get("legacy_scoring", cfg)  # Accept original saved configs.
    print("[score.py] LEGACY REPLAY ONLY: not current topic policy", file=sys.stderr)
    raw = load_json(args.raw)
    scored = load_json(args.scored)

    dimensions = cfg["dimensions"]
    weights_by_cat = cfg["category_weights"]
    rules = cfg["rules"]
    decay_by_cat = cfg["time_decay"]
    top_n = cfg["output"]["top_n"]

    now = (datetime.fromisoformat(args.now.rstrip("Z")).replace(tzinfo=timezone.utc)
           if args.now else datetime.now(timezone.utc))

    raw_by_id = {item["id"]: item for item in raw["items"]}

    ranked: list[dict] = []
    for entry in scored["items"]:
        item_id = entry["id"]
        cat = entry["category"]
        score = entry["scores"]
        evidence = entry.get("evidence_quotes", {})

        if cat not in weights_by_cat:
            raise ValueError(f"Unknown category {cat!r} for item {item_id}")

        base = aggregate(score, weights_by_cat[cat])

        keep, delta, trace = apply_rules(score, evidence, rules, dimensions)
        if not keep:
            continue

        adjusted = base + delta
        raw_item = raw_by_id[item_id]
        hours = hours_since(raw_item["publishedAt"], now)
        final = time_decay(adjusted, hours, decay_by_cat[cat])

        ranked.append({
            "id": item_id,
            "title": raw_item["title"],
            "category": cat,
            "source": raw_item.get("source"),
            "url": raw_item.get("url"),
            "published_at": raw_item["publishedAt"],
            "base_quality_score": round(base, 2),
            "adjusted_score": round(adjusted, 2),
            "final_score": round(final, 2),
            "dimensional_scores": {d: {"score": score[d],
                                        "evidence_quote": evidence.get(d, "")}
                                    for d in dimensions},
            "rule_trace": trace,
            "summary_zh": raw_item.get("summary", ""),
        })

    ranked.sort(key=lambda r: r["final_score"], reverse=True)
    ranked = ranked[:top_n]
    for i, r in enumerate(ranked, 1):
        r["rank"] = i

    out = {
        "status": "legacy_replay",
        "current_discovery_input": False,
        "fetched_at": raw.get("fetched_at"),
        "scored_at": now.isoformat(),
        "time_window_hours": raw.get("time_window_hours"),
        "total_fetched": raw.get("total_fetched", len(raw_by_id)),
        "after_gate": len(scored["items"]),
        "after_rules": len(ranked),
        "candidates": ranked,
    }

    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"[score.py] wrote {len(ranked)} ranked candidates to {args.out}")

    min_required = cfg["output"]["min_candidates_required"]
    if len(ranked) < min_required:
        print(f"[score.py] WARNING: only {len(ranked)} candidates passed (min {min_required}). "
              "Historical minimum reproduced; do not fetch more to fill a quota.", file=sys.stderr)
        return 2  # soft warning exit
    return 0


if __name__ == "__main__":
    sys.exit(main())
