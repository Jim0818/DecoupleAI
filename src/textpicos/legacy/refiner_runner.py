#!/usr/bin/env python3
"""Deterministic shell around the text-only Refiner model call."""
from __future__ import annotations
from textpicos.paths import ProjectPaths as _ProjectPaths

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

REPO = _ProjectPaths.discover().root
SKILL = REPO / "agents/decouple-refiner/SKILL.md"
# REPO is already canonical. Importing validation helpers must not probe live
# article paths; resolve only the explicitly selected article at execution.
PENDING = REPO / "articles/pending"
FENCE_RE = re.compile(r"^([ \t]*)(`{3,}|~{3,})([^\n]*)\n(.*?)(?:\n\1\2[ \t]*)(?=\n|$)", re.MULTILINE | re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,2})[ \t]+(.+?)\s*$", re.MULTILINE)
URL_RE = re.compile(r"https?://[^\s<>\])}]+")
LINK_TARGET_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+['\"][^)]*['\"])?\)")
FOOTNOTE_RE = re.compile(r"\[\^[^\]]+\]")
HTML_RE = re.compile(r"<!--.*?-->|<(?P<tag>[A-Za-z][\w:-]*)(?:\s[^<>]*?)?>.*?</(?P=tag)\s*>|<[^>]+>", re.DOTALL)
NUMBER_RE = re.compile(r"(?<![\w.-])(?:[$¥￥€£]\s*)?\d+(?:[.,]\d+)*(?:\s*(?:%|％|元|万元|亿元|美元|GB|MB|KB|TB|ms|s|秒|分钟|小时|天|年|月|日|倍|个|次|维|tokens?|QPS|FPS))?(?![\w.-])", re.IGNORECASE)
VERSION_RE = re.compile(r"\bv?\d+(?:\.\d+){1,3}(?:[-+][\w.-]+)?\b", re.IGNORECASE)
IDENT_RE = re.compile(r"`[^`\n]+`|\b[A-Za-z_][A-Za-z0-9_]*(?:(?:::|\.|/|-)[A-Za-z0-9_]+)+\b")
FORBIDDEN_INTERNAL_RE = re.compile(r"(?im)^\s*(?:TODO|FIXME|Reviewer\s+(?:instruction|brief)|policy\s+text|内部诊断|审稿指令)\s*[:：]")
PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}|\[\[(?:TODO|TBD|PLACEHOLDER)[^\]]*\]\]", re.IGNORECASE)


class RefinerError(ValueError):
    pass


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def repo_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO / path


def _refiner_typed_input_ref(dispatch: dict[str, Any]) -> str:
    """Resolve the v4.2 typed-input ref from the envelope or its input bundle."""
    typed_ref = dispatch.get("typed_input_ref")
    if isinstance(typed_ref, str) and typed_ref and repo_path(typed_ref).is_file():
        return typed_ref
    bundle = json.loads(repo_path(dispatch["input_bundle_ref"]).read_text(encoding="utf-8"))
    typed_ref = (bundle.get("typed_input_ref") or "").strip()
    if not typed_ref or not repo_path(typed_ref).is_file():
        raise RefinerError("v4.2 Refiner typed_input_ref is required")
    return typed_ref


def load_dispatch(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("phase") not in {"REFINER", "V41_REFINER", "V42_REFINER"}:
        raise RefinerError("dispatch is not a Refiner job")
    if data.get("model_route") != "highest_quality_text" or data.get("tool_permissions") != []:
        raise RefinerError("Refiner requires highest_quality_text and empty tool permissions")
    return data


def article_from_dispatch(dispatch: dict[str, Any]) -> tuple[Path, str]:
    bundle = json.loads(repo_path(dispatch["input_bundle_ref"]).read_text(encoding="utf-8"))
    ref = (bundle.get("semantic_refs") or {}).get("article_path")
    if not isinstance(ref, str) or not ref.strip():
        raise RefinerError("article_path is missing")
    article = repo_path(ref).resolve()
    try:
        article.relative_to(PENDING)
    except ValueError as exc:
        raise RefinerError("article_path must be under articles/pending") from exc
    if not article.is_file() or "visuals" in article.parts:
        raise RefinerError("article_path is not a pending Markdown article")
    return article, str(article.relative_to(REPO))


def _v42_system_prompt(dispatch: dict[str, Any]) -> tuple[str, list[str]]:
    """Inline the same capsule selection used by the legacy dispatcher.

    This model route has no tools: a path mentioned inside the runtime is not
    loaded content. Keep selection in dispatch, then materialize each actual
    resource once instead of silently falling back to the complete old Skill.
    """
    from textpicos.legacy.engine.dispatch import select_skill_capsules

    if (dispatch.get("context") or {}).get("writing_policy_version") != "v4_2_content_first":
        raise RefinerError("V42_REFINER requires explicit v4_2_content_first context")
    try:
        refs = select_skill_capsules(
            dispatch, {"id": "V42_REFINER", "executor": "decouple-refiner"}, {},
        )
        parts, loaded, seen = [], [], set()
        for ref in refs:
            path = repo_path(ref)
            resolved = path.resolve()
            if resolved in seen:
                continue
            content = path.read_text(encoding="utf-8")
            if not content.strip():
                raise RefinerError(f"Refiner prompt resource is empty: {ref}")
            seen.add(resolved)
            loaded.append(ref)
            parts.append(f"<!-- resource: {ref} -->\n{content.rstrip()}")
    except (OSError, ValueError) as exc:
        raise RefinerError(f"Cannot prepare v4.2 Refiner methods: {exc}") from exc
    return "\n\n".join(parts), loaded


def prepare(dispatch_path: Path) -> dict[str, Any]:
    dispatch = load_dispatch(dispatch_path)
    article, article_ref = article_from_dispatch(dispatch)
    original = article.read_text(encoding="utf-8")
    if not original.strip():
        raise RefinerError("article is empty")
    staging = repo_path(dispatch["staging_dir"])
    staging.mkdir(parents=True, exist_ok=True)
    snapshot = staging / "article.before.md"
    payload = staging / "llm-payload.json"
    response = staging / "model-response.md"
    snapshot.write_text(original, encoding="utf-8")

    if dispatch.get("phase") == "V42_REFINER":
        typed_ref = _refiner_typed_input_ref(dispatch)
        typed = json.loads(repo_path(typed_ref).read_text(encoding="utf-8"))
        review_ref = typed.get("body_review_report_ref")
        if not isinstance(review_ref, str) or not repo_path(review_ref).is_file():
            raise RefinerError("v4.2 body_review_report_ref is required")
        review = json.loads(repo_path(review_ref).read_text(encoding="utf-8"))
        system_text, system_refs = _v42_system_prompt(dispatch)
        user_payload = {
            "task": "Repair only the named local findings. Return exactly one JSON object and no prose.",
            "article_markdown": original,
            "body_review": review,
            "repair_contract": typed,
            "response_contract": {
                "article_markdown": "complete revised Markdown article",
                "resolved_finding_ids": "array of allowed finding IDs fully resolved",
                "unresolved_finding_ids": "array of allowed finding IDs not safely resolved",
                "change_manifest": [{"finding_id": "BR-...", "locations": ["section/anchor"], "change_type": "clarify|compress|transition|evidence_exposition"}],
                "claim_boundaries_preserved": True,
            },
        }
        payload_data = {"system": system_text, "user": json.dumps(user_payload, ensure_ascii=False, indent=2)}
    else:
        payload_data = {"system": SKILL.read_text(encoding="utf-8"), "user": original}
        system_refs = [str(SKILL.relative_to(REPO))]
    payload.write_text(json.dumps(payload_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "article_path": article_ref,
        "before_sha256": sha256(original),
        "snapshot_path": str(snapshot.relative_to(REPO)),
        "payload_path": str(payload.relative_to(REPO)),
        "response_path": str(response.relative_to(REPO)),
        "runtime": dispatch.get("phase"),
        "system_resource_refs": system_refs,
    }
    (staging / "refiner-run.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest

def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise RefinerError("YAML front matter is required")
    end = text.find("\n---", 4)
    if end < 0:
        raise RefinerError("YAML front matter is unterminated")
    value = yaml.safe_load(text[4:end]) or {}
    if not isinstance(value, dict):
        raise RefinerError("YAML front matter must be an object")
    return value, text[end + 4:].lstrip("\n")


def _extract(pattern: re.Pattern[str], text: str) -> list[str]:
    values = []
    for match in pattern.finditer(text):
        values.append(match.group(0))
    return values


def _quote_blocks(text: str) -> list[str]:
    blocks, current = [], []
    for line in text.splitlines():
        if line.startswith(">"):
            current.append(line)
        elif current:
            blocks.append("\n".join(current)); current = []
    if current:
        blocks.append("\n".join(current))
    return blocks


def _heading_integrity_errors(
    original: str,
    candidate: str,
    *,
    allow_h2_change: bool = False,
) -> list[str]:
    """Protect H1 always; let v4.2 structure repairs change H2 only when authorized."""
    errors: list[str] = []
    before_heads = [(m.group(1), m.group(2)) for m in HEADING_RE.finditer(original)]
    after_heads = [(m.group(1), m.group(2)) for m in HEADING_RE.finditer(candidate)]
    before_h1 = [title for level, title in before_heads if level == "#"]
    after_h1 = [title for level, title in after_heads if level == "#"]
    if before_h1 != after_h1:
        errors.append("H1 text/count/order changed")
    if not allow_h2_change:
        before_h2 = [title for level, title in before_heads if level == "##"]
        after_h2 = [title for level, title in after_heads if level == "##"]
        if before_h2 != after_h2:
            errors.append("H2 count/order/text changed without an authorized structure finding")
    return errors


def _v42_allows_h2_change(typed: dict[str, Any], review: dict[str, Any]) -> bool:
    allowed = set(typed.get("allowed_finding_ids") or [])
    return any(
        isinstance(item, dict)
        and item.get("id") in allowed
        and item.get("category") == "structure"
        for item in (review.get("findings") or [])
    )


def validate(
    original: str,
    candidate: str,
    article: Path,
    *,
    allow_h2_change: bool = False,
) -> list[str]:
    errors: list[str] = []
    stripped = candidate.strip()
    if not stripped:
        return ["output is empty"]
    if stripped.startswith("```") or stripped.startswith("~~~"):
        errors.append("output must not be wrapped in a code fence")
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
            errors.append("JSON output is forbidden")
        except json.JSONDecodeError:
            pass
    if re.match(r"^(?:已完成|以下是|精修后|修改说明|说明[:：])", stripped):
        errors.append("explanatory prefix is forbidden")
    try:
        before_fm, _ = _frontmatter(original)
        after_fm, _ = _frontmatter(candidate)
        if before_fm != after_fm:
            errors.append("YAML front matter values changed")
    except (RefinerError, yaml.YAMLError) as exc:
        errors.append(str(exc))
    before_fences = [(m.group(2), m.group(3).strip(), m.group(4)) for m in FENCE_RE.finditer(original)]
    after_fences = [(m.group(2), m.group(3).strip(), m.group(4)) for m in FENCE_RE.finditer(candidate)]
    if before_fences != after_fences:
        errors.append("fenced code blocks changed")
    for label, pattern in (("URLs", URL_RE), ("Markdown link targets", LINK_TARGET_RE),
                           ("footnotes", FOOTNOTE_RE), ("HTML/SVG/UI markers", HTML_RE),
                           ("high-risk numeric tokens", NUMBER_RE), ("versions", VERSION_RE),
                           ("code identifiers", IDENT_RE)):
        if _extract(pattern, original) != _extract(pattern, candidate):
            errors.append(f"{label} changed")
    if _quote_blocks(original) != _quote_blocks(candidate):
        errors.append("quoted external text changed")
    errors.extend(_heading_integrity_errors(original, candidate, allow_h2_change=allow_h2_change))
    if FORBIDDEN_INTERNAL_RE.search(candidate) and not FORBIDDEN_INTERNAL_RE.search(original):
        errors.append("internal diagnostic or instruction text was added")
    if PLACEHOLDER_RE.search(candidate) and not PLACEHOLDER_RE.search(original):
        errors.append("unresolved placeholder was added")
    sys.path.insert(0, str(REPO / "scripts"))
    import textpicos.content.article_contract as article_contract
    contract_dir = article.parent / ".refiner-contract"
    contract_dir.mkdir(exist_ok=True)
    staging = contract_dir / article.name
    staging.write_text(candidate, encoding="utf-8")
    try:
        result = article_contract.validate_article(staging, "draft")
    finally:
        staging.unlink(missing_ok=True)
        contract_dir.rmdir()
    if not result.get("valid"):
        errors.extend(
            f"article_contract:{item.get('field')}: {item.get('message')}"
            for item in result.get("findings", [])
        )
    return list(dict.fromkeys(errors))


def _atomic_write(path: Path, text: str) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.replace(name, path)
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise


def finalize(dispatch_path: Path, response_path: Path | None = None) -> dict[str, Any]:
    dispatch = load_dispatch(dispatch_path)
    article, article_ref = article_from_dispatch(dispatch)
    staging = repo_path(dispatch["staging_dir"])
    run = json.loads((staging / "refiner-run.json").read_text(encoding="utf-8"))
    original = (REPO / run["snapshot_path"]).read_text(encoding="utf-8")
    if sha256(article.read_text(encoding="utf-8")) != run["before_sha256"]:
        raise RefinerError("article changed after Refiner snapshot; refusing stale overwrite")
    response = response_path or (REPO / run["response_path"])
    response_text = response.read_text(encoding="utf-8")
    change_manifest_path: Path | None = None
    allow_h2_change = False

    if dispatch.get("phase") == "V42_REFINER":
        stripped = response_text.strip()
        if stripped.startswith("```"):
            match = re.fullmatch(r"```(?:json)?\s*\n([\s\S]*?)\n```", stripped, re.IGNORECASE)
            if not match:
                raise RefinerError("v4.2 Refiner response must be one JSON object")
            stripped = match.group(1)
        try:
            response_data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise RefinerError(f"v4.2 Refiner response is invalid JSON: {exc}") from exc
        if not isinstance(response_data, dict):
            raise RefinerError("v4.2 Refiner response must be an object")
        candidate = response_data.pop("article_markdown", None)
        if not isinstance(candidate, str):
            raise RefinerError("v4.2 Refiner response is missing article_markdown")
        typed = json.loads(repo_path(_refiner_typed_input_ref(dispatch)).read_text(encoding="utf-8"))
        review_ref = typed.get("body_review_report_ref")
        review = json.loads(repo_path(review_ref).read_text(encoding="utf-8")) if isinstance(review_ref, str) else {}
        allow_h2_change = _v42_allows_h2_change(typed, review)
        allowed = list(typed.get("allowed_finding_ids") or [])
        resolved = list(response_data.get("resolved_finding_ids") or [])
        unresolved = list(response_data.get("unresolved_finding_ids") or [])
        if set(resolved) | set(unresolved) != set(allowed) or set(resolved) & set(unresolved):
            raise RefinerError("resolved/unresolved finding IDs must partition allowed_finding_ids exactly")
        manifest_ids = {
            item.get("finding_id") for item in response_data.get("change_manifest", [])
            if isinstance(item, dict)
        }
        if not manifest_ids.issubset(set(resolved)):
            raise RefinerError("change_manifest may only reference resolved finding IDs")
        if response_data.get("claim_boundaries_preserved") is not True:
            raise RefinerError("claim_boundaries_preserved must be true")
        sys.path.insert(0, str(REPO / "scripts"))
        from textpicos.legacy.wf_state import validate_data
        response_data["article_path"] = article_ref
        # Validate the canonical manifest after injecting the repository article path.
        schema_errors = validate_data(REPO / "workflows/schemas/refiner-v4_2-output.schema.json", response_data)
        if schema_errors:
            raise RefinerError("; ".join(schema_errors))
        change_manifest_path = staging / "refiner-change-manifest.json"
        change_manifest_path.write_text(json.dumps(response_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        candidate = response_text

    errors = validate(original, candidate, article, allow_h2_change=allow_h2_change)
    report = {
        "article_path": article_ref,
        "before_sha256": run["before_sha256"],
        "after_sha256": sha256(candidate),
        "changed": candidate != original,
        "validation_passed": not errors,
        "validation_errors": errors,
    }
    report_path = staging / "refiner-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifact_refs = [article_ref]
    if change_manifest_path is not None:
        artifact_refs.append(str(change_manifest_path.relative_to(REPO)))
    else:
        artifact_refs.append(str(report_path.relative_to(REPO)))
    receipt = {
        "job_id": dispatch["job_id"], "attempt": dispatch["attempt"],
        "dispatch_token": dispatch["dispatch_token"],
        "status": "submitted" if not errors else "failed",
        "artifact_refs": artifact_refs,
        "outcome": "DONE" if not errors else "VALIDATION_FAILED",
        "warnings": [], "diagnostics": report,
    }
    repo_path(dispatch["receipt_path"]).write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if errors:
        raise RefinerError("; ".join(errors))
    _atomic_write(article, candidate)
    return report

def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare"); prep.add_argument("dispatch", type=Path)
    finish = sub.add_parser("finalize"); finish.add_argument("dispatch", type=Path); finish.add_argument("--response", type=Path)
    args = parser.parse_args()
    try:
        result = prepare(args.dispatch) if args.command == "prepare" else finalize(args.dispatch, args.response)
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"valid": True, **result}, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    sys.exit(main())
