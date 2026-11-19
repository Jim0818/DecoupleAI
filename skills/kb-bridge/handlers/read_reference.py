#!/usr/bin/env python3
"""kb-bridge-read-reference — fuzzy chunk search over reference_materials/.

Modes:
  A (default) {query, top_n, max_chunk_chars}     -> BM25 chunk search
  B           {path}                              -> direct full-file read
  C           {module | topic_file | topic, top_n} -> 选题/模块关联素材（REFERENCE_INDEX.json）

Output A/B: [{file, chunk, score, line_start, line_end}]
Output C:   [{file, title, url, summary, modules}]
"""
import json
import sys
from common.lib import (  # noqa: E402
    AI_WIKI_ROOT, read_stdin_json, emit, err, require_vault,
    iter_md, tokenize, bm25_score,
)

CONTEXT_LINES = 12  # ± lines around hit
REFERENCE_INDEX = "/Users/jim/.claude/skills/kb-reference-index/REFERENCE_INDEX.json"


def mode_c(inp):
    """{module|topic_file|topic} -> articles mapped to that module/topic.
    Reads REFERENCE_INDEX.json (built by kb-reference-index). Soft-empty if absent."""
    module = (inp.get("module") or "").strip()
    topic_file = (inp.get("topic_file") or "").strip()
    topic = (inp.get("topic") or "").strip().lower()
    top_n = int(inp.get("top_n") or 20)

    try:
        with open(REFERENCE_INDEX, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        emit([])
    except json.JSONDecodeError:
        err("REFERENCE_INDEX.json is not valid JSON", code="INDEX_CORRUPT")

    # normalize topic_file: accept with/without 选题库/ prefix and .md suffix
    tf_norm = topic_file
    if tf_norm and not tf_norm.endswith(".md"):
        tf_norm += ".md"

    out = []
    for a in data.get("articles", []):
        hit = False
        if module and module in (a.get("modules") or []):
            hit = True
        if not hit and tf_norm:
            if any(tf_norm == t or tf_norm.endswith(t) or t.endswith(tf_norm)
                   for t in (a.get("target_topic_files") or [])):
                hit = True
        if not hit and topic:
            hay = " ".join([a.get("title") or "",
                            " ".join(a.get("suggested_topics") or []),
                            " ".join(a.get("key_concepts") or [])]).lower()
            if topic in hay:
                hit = True
        if hit:
            out.append({
                "file": a.get("file"),
                "title": a.get("title"),
                "url": a.get("url"),
                "summary": a.get("summary"),
                "modules": a.get("modules") or [],
            })
    emit(out[:top_n])


def main():
    inp = read_stdin_json()
    require_vault()

    # Mode C: 选题/模块关联素材
    if inp.get("module") or inp.get("topic_file") or inp.get("topic"):
        mode_c(inp)

    # Direct file access mode: {path: "05_synthesis/竞品技法手册.md"}
    path_param = inp.get("path")
    if path_param:
        target = (AI_WIKI_ROOT / path_param).resolve()
        try:
            target.relative_to(AI_WIKI_ROOT.resolve())
        except ValueError:
            err(f"path escapes vault: {path_param}", code="UNSAFE_PATH")
        if not target.is_file():
            err(f"file not found: {path_param}", code="PATH_NOT_FOUND")
        text = target.read_text(encoding="utf-8", errors="replace")
        emit([{
            "file": path_param,
            "chunk": text,
            "score": 1.0,
            "line_start": 1,
            "line_end": len(text.splitlines()),
        }])

    query = (inp.get("query") or "").strip()
    if not query:
        emit([])
    top_n = int(inp.get("top_n") or 10)
    max_chars = int(inp.get("max_chunk_chars") or 1500)

    ref_root = AI_WIKI_ROOT / "reference_materials"
    if not ref_root.is_dir():
        err(f"reference_materials dir not found: {ref_root}", code="PATH_NOT_FOUND")

    q_tokens = tokenize(query)
    q_set = set(q_tokens)
    if not q_set:
        emit([])

    candidates = []
    for path in iter_md(ref_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        lines = text.splitlines()
        # Find lines containing any query token (cheap pre-filter)
        hit_lines = [
            i for i, ln in enumerate(lines)
            if set(tokenize(ln)) & q_set
        ]
        if not hit_lines:
            continue
        # Cluster nearby hits into chunks
        clusters = []
        current = [hit_lines[0]]
        for ln in hit_lines[1:]:
            if ln - current[-1] <= CONTEXT_LINES * 2:
                current.append(ln)
            else:
                clusters.append(current)
                current = [ln]
        clusters.append(current)

        for cluster in clusters:
            start = max(0, cluster[0] - CONTEXT_LINES)
            end = min(len(lines), cluster[-1] + CONTEXT_LINES + 1)
            chunk = "\n".join(lines[start:end])
            if len(chunk) > max_chars:
                chunk = chunk[:max_chars] + "…"
            score = bm25_score(q_tokens, tokenize(chunk))
            candidates.append({
                "file": str(path.relative_to(AI_WIKI_ROOT)),
                "chunk": chunk,
                "score": round(score, 4),
                "line_start": start + 1,
                "line_end": end,
            })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    emit(candidates[:top_n])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
