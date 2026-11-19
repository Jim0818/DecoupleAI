#!/usr/bin/env python3
"""kb-bridge-retrieve — semantic search over AI-WIKI/04_wiki/**.

Input  (stdin JSON): {query, domain?, recency?, account?, top_n=10}
Output (stdout JSON): [{path, title, tldr, score, type, tags, account, used_in}]
"""
import sys
from datetime import date, datetime, timedelta
from common.lib import (  # noqa: E402
    AI_WIKI_ROOT, read_stdin_json, emit, err, require_vault,
    read_md, iter_md, tokenize, bm25_score, tldr_from_body,
)

DOMAIN_TAGS = {
    "ai-infra": {"ai-infra", "serving", "training"},
    "agents":   {"agent", "agents", "multi-agent"},
    "llm":      {"llm", "model", "reasoning"},
    "protocols":{"mcp", "protocol", "a2a"},
    "coding":   {"coding", "claude-code", "agentic-coding"},
    "visual":   {"visual", "svg", "diagram"},
}
RECENCY_DAYS = {"7d": 7, "30d": 30, "90d": 90, "all": None}


def main():
    inp = read_stdin_json()
    query = (inp.get("query") or "").strip()
    if not query:
        emit([])
    require_vault()

    domain = inp.get("domain")
    account = inp.get("account") or "all"
    recency = inp.get("recency") or "all"
    top_n = int(inp.get("top_n") or 10)

    wiki_root = AI_WIKI_ROOT / "04_wiki"
    if not wiki_root.is_dir():
        err(f"wiki root not found: {wiki_root}", code="PATH_NOT_FOUND")
    cutoff = None
    if RECENCY_DAYS.get(recency):
        cutoff = date.today() - timedelta(days=RECENCY_DAYS[recency])

    domain_tag_set = DOMAIN_TAGS.get(domain) if domain else None
    q_tokens = tokenize(query)
    if not q_tokens:
        emit([])

    results = []
    for path in iter_md(wiki_root):
        try:
            fm, body = read_md(path)
        except Exception:
            continue

        # Account filter (all matches anything)
        if account != "all":
            doc_acct = fm.get("account") or "all"
            if doc_acct not in (account, "all"):
                continue

        # Domain filter via tag intersection
        if domain_tag_set:
            doc_tags = set(fm.get("tags") or [])
            if not doc_tags & domain_tag_set:
                continue

        # Recency filter
        if cutoff:
            updated = fm.get("updated") or fm.get("created")
            if not updated:
                continue
            if isinstance(updated, str):
                try:
                    updated = datetime.fromisoformat(updated).date()
                except ValueError:
                    continue
            elif isinstance(updated, datetime):
                updated = updated.date()
            if updated < cutoff:
                continue

        # Score: BM25 over title + body
        title = str(fm.get("title") or path.stem)
        doc_text = f"{title}\n{body}"
        d_tokens = tokenize(doc_text)
        score = bm25_score(q_tokens, d_tokens)
        if score <= 0:
            continue

        results.append({
            "path": str(path.relative_to(AI_WIKI_ROOT)),
            "title": title,
            "tldr": tldr_from_body(body),
            "score": round(score, 4),
            "type": fm.get("type"),
            "tags": fm.get("tags") or [],
            "account": fm.get("account") or "all",
            "used_in": fm.get("used_in") or [],
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    emit(results[:top_n])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err(f"{type(e).__name__}: {e}", code="INTERNAL")
