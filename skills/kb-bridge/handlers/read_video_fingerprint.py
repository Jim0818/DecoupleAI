#!/usr/bin/env python3
"""Read medium-isolated video fingerprints from AI-WIKI exemplars."""
from pathlib import Path

from common.lib import AI_WIKI_ROOT, emit, err, iter_md, read_md, read_stdin_json, require_vault


def main():
    inp = read_stdin_json()
    account = inp.get("account")
    medium = inp.get("medium", "douyin")
    top_n = int(inp.get("top_n", 5))
    layer = inp.get("layer")
    include_composite = bool(inp.get("include_composite", False))
    min_viral = float(inp.get("min_viral_score", 0.0))
    if medium not in {"douyin", "weixin-video"}:
        err("medium must be douyin or weixin-video", code="INVALID_MEDIUM")
    require_vault()

    results = []
    for path in iter_md(AI_WIKI_ROOT / "exemplars"):
        if not path.name.endswith("-fingerprint.md"):
            continue
        if not include_composite and path.stem.startswith("_account-composite"):
            continue
        try:
            fm, body = read_md(path)
        except Exception:
            continue
        if fm.get("medium") != medium:
            continue
        if account and fm.get("account") != account and account not in path.parts:
            continue
        if float(fm.get("viral_score") or 0) < min_viral:
            continue
        item = dict(fm)
        item.setdefault("slug", path.stem.removesuffix("-fingerprint"))
        item["_source"] = str(path.relative_to(AI_WIKI_ROOT))
        if layer:
            key = f"layer_{layer}"
            item = {
                k: item.get(k)
                for k in ("slug", "account", "medium", "viral_score", "hook_type", "fit_level", key)
                if item.get(k) is not None
            }
        results.append(item)

    results.sort(key=lambda item: float(item.get("viral_score") or 0), reverse=True)
    selected = results if top_n == -1 else results[:max(0, top_n)]
    summary = None
    if selected:
        summary = selected[0].get("style_summary") or selected[0].get("layer_account", {}).get("positioning")
    emit({
        "medium": medium,
        "account": account,
        "total_count": len(selected),
        "fingerprints": selected,
        "account_style_summary": summary,
        "fallback": not bool(selected),
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        err(f"{type(exc).__name__}: {exc}", code="INTERNAL")
