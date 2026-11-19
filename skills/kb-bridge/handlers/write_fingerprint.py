#!/usr/bin/env python3
"""kb-bridge-write-fingerprint — style-analyst fingerprint writer.

Input: {slug, account, column?, viral_score?, hook_pattern?, tone?,
        rhetoric_devices?, structure?, fingerprint_text}
Output: {fingerprint_path, linked_card}
"""
from datetime import date as date_cls
from common.lib import (  # noqa: E402
    AI_WIKI_ROOT, read_stdin_json, emit, err, require_vault,
    read_md, write_md_atomic, append_log, normalize_fit_level,
)

ACCOUNTS = {"decoupleai", "studio", "intellifuture"}


def main():
    inp = read_stdin_json()
    slug = inp.get("slug")
    account = inp.get("account")
    if not slug or not account:
        err("slug and account required", code="BAD_INPUT")
    if account not in ACCOUNTS:
        err(f"invalid account: {account}", code="INVALID_ACCOUNT")
    require_vault()

    fp_path = AI_WIKI_ROOT / "exemplars" / account / f"{slug}-fingerprint.md"
    fp_path.parent.mkdir(parents=True, exist_ok=True)

    today = str(date_cls.today())
    if fp_path.exists():
        try:
            fm, _old_body = read_md(fp_path)
        except Exception:
            fm = {}
    else:
        fm = {
            "title": f"{slug} — fingerprint",
            "type": "source",
            "status": "stable",
            "created": today,
            "confidence": "extracted",
            "tags": ["fingerprint", "style"],
            "account": account,
        }

    # Merge updates
    fm["updated"] = today
    new_fit_level = normalize_fit_level(
        inp.get("fit_level", inp.get("account_fit", inp.get("account_fit_score")))
    )
    if new_fit_level is None:
        new_fit_level = normalize_fit_level(
            fm.get("fit_level", fm.get("account_fit", fm.get("account_fit_score")))
        )
    if new_fit_level:
        fm["fit_level"] = new_fit_level
        fm.pop("account_fit", None)
        fm.pop("account_fit_score", None)
        fm.pop("fit_score", None)
    for k in (
        "column", "viral_score", "hook_pattern", "tone", "rhetoric_devices", "structure",
        "fit_detail", "adaptation",
        "medium", "medium_tags", "hook_type", "structure_template",
        "info_density_ratio", "source_viral_slug",
    ):
        v = inp.get(k)
        if v is not None:
            fm[k] = v

    # Auto-link article card if present
    card_path = AI_WIKI_ROOT / "04_wiki" / "articles" / f"{slug}.md"
    linked_card = None
    if card_path.exists():
        fm["article_card"] = f"[[04_wiki/articles/{slug}]]"
        linked_card = str(card_path.relative_to(AI_WIKI_ROOT))
        # bidirectional: write back to card
        try:
            card_fm, card_body = read_md(card_path)
            card_fm["fingerprint"] = f"[[exemplars/{account}/{slug}-fingerprint]]"
            card_fm["updated"] = today
            write_md_atomic(card_path, card_fm, card_body)
        except Exception:
            pass

    body = (
        f"## TL;DR\n\n{slug} 的风格指纹快照（{today}）。\n\n"
        f"## Fingerprint\n\n{inp.get('fingerprint_text','').strip() or '_(empty)_'}\n"
    )
    write_md_atomic(fp_path, fm, body)

    append_log("kb-bridge-write-fingerprint", slug, {
        "fingerprint_path": str(fp_path.relative_to(AI_WIKI_ROOT)),
        "account": account,
        "linked_card": linked_card or "(none)",
    })
    emit({
        "fingerprint_path": str(fp_path.relative_to(AI_WIKI_ROOT)),
        "linked_card": linked_card,
        "fit_level": fm.get("fit_level"),
    })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
