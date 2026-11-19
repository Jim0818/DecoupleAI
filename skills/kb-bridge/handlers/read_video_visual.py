#!/usr/bin/env python3
"""Read and aggregate video visual annotations."""
from collections import Counter

from common.lib import AI_WIKI_ROOT, emit, err, iter_md, read_md, read_stdin_json, require_vault


def dominant(values):
    values = [value for value in values if value is not None]
    return Counter(values).most_common(1)[0][0] if values else None


def main():
    inp = read_stdin_json()
    account = inp.get("account")
    medium = inp.get("medium", "douyin")
    output_type = inp.get("output_type", "suggestion")
    scene_type = inp.get("scene_type")
    if not account:
        err("account required", code="BAD_INPUT")
    if medium not in {"douyin", "weixin-video"}:
        err("medium must be douyin or weixin-video", code="INVALID_MEDIUM")
    if output_type not in {"suggestion", "cluster"}:
        err("output_type must be suggestion or cluster", code="BAD_INPUT")
    require_vault()

    samples = []
    for path in iter_md(AI_WIKI_ROOT / "exemplars"):
        if not path.name.endswith("-visual.md"):
            continue
        try:
            fm, _ = read_md(path)
        except Exception:
            continue
        if fm.get("medium") != medium:
            continue
        if fm.get("account") != account and account not in path.parts:
            continue
        primary_scene = (fm.get("scene_type") or {}).get("primary")
        if scene_type and scene_type != primary_scene:
            continue
        sample = dict(fm)
        sample["_source"] = str(path.relative_to(AI_WIKI_ROOT))
        samples.append(sample)

    if not samples:
        emit({
            "medium": medium,
            "account": account,
            "has_visual_data": False,
            "production_suggestions": None,
            "sample_count": 0,
            "fallback_reason": f"no matching visual annotations for {account}/{medium}",
        })
    if output_type == "cluster":
        emit({
            "medium": medium,
            "account": account,
            "has_visual_data": True,
            "samples": samples,
            "sample_count": len(samples),
        })

    frames = [sample.get("frame_structure", {}) for sample in samples]
    shots = [sample.get("shot_language", {}) for sample in samples]
    symbols = [sample.get("visual_symbols", {}) for sample in samples]
    editing = [sample.get("editing_rhythm", {}) for sample in samples]
    cluster = {
        "dominant_frame_structures": sorted({item.get("dominant") for item in frames if item.get("dominant")}),
        "dominant_shots": sorted({item.get("dominant_shot") for item in shots if item.get("dominant_shot")}),
        "subtitle_bar": any(item.get("subtitle_bar") for item in symbols),
        "bgm_emotion_pattern": dominant(item.get("bgm_emotion") for item in symbols),
        "visual_symbols": sorted({item.get("subtitle_style") for item in symbols if item.get("subtitle_style")}),
        "brand_color_tendency": dominant(item.get("brand_color") for item in symbols),
    }
    suggestions = {
        "opening_frame": f"优先使用 {dominant(item.get('first_frame_type') for item in frames) or '内容证明画面'}",
        "shot_sequence": "人物建立信任，录屏或产品画面提供证据；按内容类型调节占比",
        "transition_style": dominant(item.get("primary_transition") for item in editing) or "cut",
        "visual_symbols_to_use": cluster["visual_symbols"],
        "bgm_suggestion": cluster["bgm_emotion_pattern"],
    }
    emit({
        "medium": medium,
        "account": account,
        "has_visual_data": True,
        "visual_style_cluster": cluster,
        "production_suggestions": suggestions,
        "data_source": f"exemplars/**/{account}/*-visual.md",
        "sample_count": len(samples),
        "fallback_reason": None,
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        err(f"{type(exc).__name__}: {exc}", code="INTERNAL")
