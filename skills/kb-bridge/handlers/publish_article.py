#!/usr/bin/env python3
"""Publish one current native delivery and enhance its explicit wiki destination.

Input: {article_path, target_path?, force?: bool, dry_run?: bool, run_id?, optional?}
article_path selects one Markdown file within TEXTPICOS_ROOT. Its frontmatter is
the only source of article identity. target_path is relative to the explicitly
configured vault, or an absolute path within it; the default is
articles/published/<account>/<column>/<slug>/<article filename>.

Output: {status, published_path, wiki_card_path, used_in_updated, registry,
         pending_sources_retained, changed, source_version, published_version}
Every invocation verifies the current completed supervisor run, even a repeat.
Publication copies the selected article and its referenced images; source files
remain in place. dry_run validates without publishing or writing wiki/cache data.
"""
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from common.lib import (
    AI_WIKI_ROOT, read_stdin_json, emit, err, require_vault, textpicos_root,
    read_md, write_md_atomic, load_cache, save_cache, sha256_of,
    append_log, iter_md, extract_wikilinks, tldr_from_body,
)


def _vault_path(value: str | Path) -> Path:
    root = Path(os.path.abspath(AI_WIKI_ROOT))
    raw = Path(value)
    path = Path(os.path.abspath(raw if raw.is_absolute() else root / raw))
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Publication and wiki paths must stay inside the configured vault")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("Vault publication paths must not contain symlinks")
    return path


def _enhance(article_md: Path, card_path: Path, info: dict, publication: dict, api) -> dict:
    """Enhance only the publication whose exact bytes were checked by the service."""
    blob = article_md.read_bytes()
    if {"sha256": hashlib.sha256(blob).hexdigest(), "size": len(blob)} != publication["published_version"]:
        raise ValueError("Published article changed before wiki enhancement")
    art_fm, article_body = api.split_frontmatter(blob.decode("utf-8"))
    source_ref = str(article_md.relative_to(AI_WIKI_ROOT))
    article_key = f"{info['account']}/{info['column']}/{info['slug']}"
    cache_key = "publish::" + sha256_of(article_key + "::" + info["run_id"] + "::" + publication["source_version"]["sha256"])
    cache = load_cache()
    if not isinstance(cache, dict):
        cache = {"version": 1, "entries": {}, "errors": []}
    if not isinstance(cache.get("entries"), dict):
        cache["entries"] = {}
    existing_fm, existing_body = read_md(card_path) if card_path.is_file() else ({}, "")
    if (cache_key in cache["entries"] and existing_fm.get("source_ref") == source_ref
            and existing_fm.get("source_sha256") == publication["published_version"]["sha256"]):
        return {"wiki_card_path": str(card_path.relative_to(AI_WIKI_ROOT)),
                "used_in_updated": [], "wiki_changed": False}
    referenced = list(dict.fromkeys(extract_wikilinks(article_body)))
    today = str(date.today())
    card_fm = {
        "title": art_fm["title"], "type": "article", "status": "stable",
        "created": str(existing_fm.get("created") or today), "updated": today,
        "source": "published_article", "source_ref": source_ref,
        "source_run_id": info["run_id"], "source_sha256": publication["published_version"]["sha256"],
        "confidence": "extracted", "tags": art_fm.get("tags") or [],
        "account": info["account"], "column": info["column"], "article_identity": article_key,
        "related": [f"[[{ref}]]" for ref in referenced], "used_in": existing_fm.get("used_in") or [],
    }
    card_body = (
        f"## TL;DR\n\n{tldr_from_body(article_body, 300)}\n\n## H2 大纲\n\n"
        + "\n".join(f"- {heading}" for heading in api.body_h2_titles(article_body)[:20])
        + "\n\n## 引用概念\n\n"
        + ("\n".join(f"- [[{ref}]]" for ref in referenced) if referenced else "_(none)_")
        + f"\n\n## Source\n\n`{source_ref}`\n"
    )
    # Plan node changes before writing the derived card; skip unrelated content.
    node_updates = []
    if referenced:
        referenced_set = set(referenced)
        for candidate in iter_md(_vault_path("04_wiki")):
            node_path = _vault_path(candidate)
            if node_path == card_path:
                continue
            node_fm, node_body = read_md(node_path)
            aliases = node_fm.get("aliases") or []
            if not ({node_path.stem, *[str(alias) for alias in aliases]} & referenced_set):
                continue
            used = list(node_fm.get("used_in") or [])
            if article_key not in used:
                node_fm.update(used_in=[*used, article_key], updated=today)
                node_updates.append((node_path, node_fm, node_body))
    write_md_atomic(card_path, card_fm, card_body)
    for node_path, node_fm, node_body in node_updates:
        write_md_atomic(node_path, node_fm, node_body)
    result = {"wiki_card_path": str(card_path.relative_to(AI_WIKI_ROOT)),
              "used_in_updated": [str(path.relative_to(AI_WIKI_ROOT)) for path, _, _ in node_updates],
              "wiki_changed": True}
    cache["entries"][cache_key] = result
    _vault_path("00_meta").mkdir(parents=True, exist_ok=True)
    save_cache(cache)
    append_log("kb-bridge-publish-article", info["run_id"], {
        "article_identity": article_key, "published_path": source_ref,
        "card_path": result["wiki_card_path"], "used_in_updated": len(node_updates),
    })
    return result


def main():
    inp = read_stdin_json()
    allowed = {"article_path", "target_path", "force", "dry_run", "run_id", "optional"}
    if not isinstance(inp, dict) or not isinstance(inp.get("article_path"), str) or not inp["article_path"].strip():
        err("article_path must explicitly select one Markdown file", code="BAD_INPUT")
    if set(inp) - allowed:
        err("Unsupported publish fields: " + ", ".join(sorted(set(inp) - allowed)), code="BAD_INPUT")
    if any(type(inp.get(flag, False)) is not bool for flag in ("force", "dry_run", "optional")):
        err("force, dry_run and optional must be booleans", code="BAD_INPUT")
    if "target_path" in inp and (not isinstance(inp["target_path"], str) or not inp["target_path"].strip()):
        err("target_path must be a Markdown file path", code="BAD_INPUT")
    require_vault()
    try:
        root = textpicos_root()
        sys.path.insert(0, str(root / "src"))
        from textpicos.paths import ProjectPaths
        from textpicos.content import article_contract as api, article_registry
        from textpicos.content.publication import publish_article
        if Path(api.REPO) != root:
            raise ValueError("Loaded TextPicOS package does not match the selected project")
        info = article_registry.identity(Path(inp["article_path"]), paths=ProjectPaths.from_root(root))
        article = Path(info["path"])
        if article.suffix != ".md":
            raise ValueError("article_path must select a Markdown file")
        requested_run = inp.get("run_id") or os.environ.get("TEXTPICOS_RUN_ID")
        if requested_run is not None and requested_run != info["run_id"]:
            raise ValueError("Requested run_id must match the selected article frontmatter")
        default_target = Path("articles/published") / info["account"] / info["column"] / info["slug"] / article.name
        target = _vault_path(inp.get("target_path") or default_target)
        if target.suffix != ".md":
            raise ValueError("target_path must name a Markdown file")
        card = _vault_path(Path("04_wiki/articles") / info["account"] / info["column"] / (info["slug"] + ".md"))
        if target == card:
            raise ValueError("The published article and derived wiki card need distinct paths")
        for metadata_path in ("00_meta/.wiki-cache.json", "00_meta/log.md", "04_wiki"):
            _vault_path(metadata_path)
        result = publish_article(article, target, overwrite=inp.get("force", False),
                                 dry_run=inp.get("dry_run", False), api=api)
    except (OSError, ValueError) as exc:
        err(str(exc), code="PUBLICATION_REJECTED")
    output = {**result, "published_path": str(target.relative_to(AI_WIKI_ROOT)),
              "wiki_card_path": str(card.relative_to(AI_WIKI_ROOT)), "run_id": info["run_id"]}
    if inp.get("dry_run"):
        print(json.dumps({**output, "status": "validated", "used_in_updated": []}, ensure_ascii=False))
        return
    try:
        enhancement = _enhance(target, card, info, result, api)
    except Exception as exc:
        err(f"Article published to {output['published_path']}; wiki enhancement is incomplete and can be retried: {exc}",
            code="WIKI_ENHANCEMENT_INCOMPLETE")
    emit({**output, **enhancement, "status": "published",
          "changed": result["changed"] or enhancement["wiki_changed"]})


if __name__ == "__main__":
    main()
