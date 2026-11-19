#!/usr/bin/env python3
"""kb-bridge-read-exemplar — read exemplars/{account}/ fingerprints.

Input:  {account, top=5, column?, tag?}
Output: [{slug, title, fingerprint, hook, structure, viral_score}]
"""
import re
from common.lib import (  # noqa: E402
    AI_WIKI_ROOT, read_stdin_json, emit, err, require_vault, read_md, iter_md,
    first_h2_outline, fit_level_from_record,
)


def main():
    inp = read_stdin_json()
    account = inp.get("account")
    if not account:
        err("account required", code="BAD_INPUT")
    require_vault()

    top = int(inp.get("top") or 5)
    column = inp.get("column")
    tag = inp.get("tag")
    medium = inp.get("medium", "all")
    hook_type = inp.get("hook_type")
    include_composite = bool(inp.get("include_composite", False))

    base = AI_WIKI_ROOT / "exemplars" / account
    if not base.is_dir():
        err(f"exemplars dir not found: {base}", code="PATH_NOT_FOUND")

    out = []
    for path in iter_md(base):
        if not path.name.endswith("-fingerprint.md"):
            continue
        try:
            fm, body = read_md(path)
        except Exception:
            continue
        if column and fm.get("column") != column:
            continue
        if tag and tag not in (fm.get("tags") or []):
            continue
        record_medium = fm.get("medium") or "wechat"
        if medium != "all" and record_medium != medium:
            continue
        if hook_type and fm.get("hook_type") != hook_type:
            continue
        if not include_composite and path.stem.startswith("_account-composite"):
            continue

        # Heuristic extraction of fingerprint section
        fp_text = ""
        m = re.search(r"##\s*Fingerprint[^\n]*\n(.+?)(?=\n##\s|\Z)", body,
                      re.DOTALL | re.IGNORECASE)
        if m:
            fp_text = m.group(1).strip()

        # Hook = first non-heading paragraph
        hook = ""
        for para in re.split(r"\n\s*\n", body):
            p = para.strip()
            if p and not p.startswith("#"):
                hook = p[:600]
                break

        out.append({
            "slug": path.stem.replace("-fingerprint", ""),
            "title": str(fm.get("title") or path.stem),
            "fingerprint": {
                "hook_pattern": fm.get("hook_pattern") or "",
                "structure": first_h2_outline(body)[:10],
                "tone": fm.get("tone") or "",
                "rhetoric_devices": fm.get("rhetoric_devices") or [],
                "raw_text": fp_text[:800],
            },
            "hook": hook,
            "viral_score": float(fm.get("viral_score") or 0.0),
            "medium": record_medium,
            "medium_tags": fm.get("medium_tags") or [],
            "hook_type": fm.get("hook_type") or "",
            "structure_template": fm.get("structure_template") or "",
            "info_density_ratio": fm.get("info_density_ratio"),
            "source_viral_slug": fm.get("source_viral_slug"),
            "fit_level": fit_level_from_record(fm),
            "fit_detail": fm.get("fit_detail") or {},
            "adaptation": fm.get("adaptation") or {"keep": [], "modify": [], "drop": []},
            "path": str(path.relative_to(AI_WIKI_ROOT)),
        })

    out.sort(key=lambda x: x["viral_score"], reverse=True)
    emit(out[:top])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
