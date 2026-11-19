"""Shared helpers for the current TextPicOS knowledge bridge.

The public dispatcher accepts one JSON request. External vault access requires
explicit configuration; optional run receipts belong to an existing native run.
"""

import hashlib
import json
import os
import re
import sys
import stat
import tempfile
from datetime import datetime, date
from pathlib import Path

import yaml

_VAULT_CONFIG = os.environ.get("TEXTPICOS_AI_WIKI_ROOT") or os.environ.get("AI_WIKI_ROOT")
AI_WIKI_ROOT = Path(_VAULT_CONFIG).expanduser().absolute() if _VAULT_CONFIG else None
CACHE_FILE = AI_WIKI_ROOT / "00_meta" / ".wiki-cache.json" if AI_WIKI_ROOT else None
LOG_FILE = AI_WIKI_ROOT / "00_meta" / "log.md" if AI_WIKI_ROOT else None


def textpicos_root() -> Path:
    """Use an explicit root, or this source bundle's own project; never guess a user directory."""
    configured = os.environ.get("TEXTPICOS_ROOT")
    root = Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[3]
    if not (root / "config/system/paths.json").is_file():
        raise ValueError("TEXTPICOS_ROOT must identify a current TextPicOS project")
    return root


def _native_runtime():
    root = textpicos_root()
    source = str(root / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    from textpicos.paths import ProjectPaths
    from textpicos.runtime import Runtime
    return Runtime(ProjectPaths.from_root(root))


def _request_run_id(request: dict) -> str:
    value = request.get("run_id")
    if value is None:
        value = os.environ.get("TEXTPICOS_RUN_ID")
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise ValueError("run_id must be a string")
    return value


def prepare_request(request: dict) -> None:
    """Validate an explicitly selected run before an external handler can mutate data."""
    global _LAST_INPUT
    run_id = _request_run_id(request)
    if run_id:
        runtime = _native_runtime()
        with runtime._locked(run_id):
            runtime._read(run_id)
    _LAST_INPUT = dict(request)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")

# ---------- IO ----------

def read_stdin_json() -> dict:
    """Read JSON from stdin. Returns {} if stdin empty."""
    global _LAST_INPUT
    raw = sys.stdin.read().strip()
    _LAST_INPUT = json.loads(raw) if raw else {}
    return _LAST_INPUT

def emit(obj) -> None:
    """Print JSON to stdout and exit 0."""
    count = len(obj) if isinstance(obj, list) else (1 if obj else 0)
    _write_receipt("ok", count)
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=_default_json))
    sys.exit(0)

def err(message: str, code: str = "ERROR") -> None:
    """Emit a soft-error JSON and exit 0 (per design: errors are data, not exceptions)."""
    if _LAST_INPUT.get("optional"):
        _write_receipt("not_available", 0, code)
        print(json.dumps({"status": "not_available", "error": code, "message": message}, ensure_ascii=False))
        sys.exit(0)
    _write_receipt("error", 0, code)
    print(json.dumps({"error": code, "message": message}, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)

def _default_json(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not serializable: {type(o)}")

# ---------- Vault ----------

def require_vault() -> None:
    if os.environ.get("TEXTPICOS_MAINTENANCE_SCOPE") == "system":
        err("External vault access is outside system maintenance scope", code="OUT_OF_SCOPE")
    if AI_WIKI_ROOT is None:
        err("Set AI_WIKI_ROOT or TEXTPICOS_AI_WIKI_ROOT explicitly", code="VAULT_NOT_CONFIGURED")
    if not AI_WIKI_ROOT.is_dir():
        err(f"AI-WIKI vault not found at {AI_WIKI_ROOT}", code="AI_WIKI_NOT_FOUND")

# ---------- Frontmatter ----------

def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Empty dict if no frontmatter."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, m.group(2)

def dump_frontmatter(fm: dict, body: str) -> str:
    """Render frontmatter + body back into a single string."""
    yml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{yml}\n---\n\n{body.lstrip()}"

def read_md(path: Path) -> tuple[dict, str]:
    return parse_frontmatter(path.read_text(encoding="utf-8"))

def write_md_atomic(path: Path, fm: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = dump_frontmatter(fm, body)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)

# ---------- SHA256 cache ----------

def load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {"version": 1, "entries": {}, "errors": []}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "entries": {}, "errors": []}

def save_cache(cache: dict) -> None:
    tmp = CACHE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CACHE_FILE)

def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# ---------- Log ----------

def append_log(skill: str, run_id: str, summary: dict) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"\n## {ts} | {skill} | {run_id}"]
    for k, v in summary.items():
        lines.append(f"- {k}: {v}")
    # prepend after frontmatter
    if LOG_FILE.exists():
        fm, body = read_md(LOG_FILE)
        new_body = "\n".join(lines) + "\n\n" + body
        write_md_atomic(LOG_FILE, fm, new_body)
    else:
        LOG_FILE.write_text("\n".join(lines), encoding="utf-8")

# ---------- Search helpers ----------

def iter_md(root: Path):
    """Yield all .md files under root, skipping dot-dirs."""
    if not root.is_dir():
        return
    for p in root.rglob("*.md"):
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        yield p

def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-word. Keep CJK as single chars (each char a token)."""
    out = []
    for chunk in re.findall(r"[A-Za-z0-9_]+|[一-鿿]", text.lower()):
        out.append(chunk)
    return out

def bm25_score(query_tokens: list[str], doc_tokens: list[str], avgdl: float = 500.0,
               k1: float = 1.5, b: float = 0.75) -> float:
    """Cheap BM25 (no IDF — corpus-level IDF would need a precomputed index).
    Treats every query token as equally rare. Sufficient for first-pass ranking."""
    if not doc_tokens:
        return 0.0
    dl = len(doc_tokens)
    from collections import Counter
    tf = Counter(doc_tokens)
    score = 0.0
    for q in query_tokens:
        f = tf.get(q, 0)
        if f == 0:
            continue
        norm = (1 - b) + b * (dl / avgdl)
        score += (f * (k1 + 1)) / (f + k1 * norm)
    return score

def extract_wikilinks(body: str) -> list[str]:
    """Return list of wikilink targets (just the target slug, not aliases)."""
    return [m.strip() for m in WIKILINK_RE.findall(body)]

def first_h2_outline(body: str) -> list[str]:
    return [line[3:].strip() for line in body.splitlines() if line.startswith("## ")]

def tldr_from_body(body: str, max_chars: int = 300) -> str:
    """Extract '## TL;DR' section or first non-empty paragraph after frontmatter."""
    m = re.search(r"##\s*TL;DR[^\n]*\n(.+?)(?=\n##\s|\Z)", body, re.DOTALL | re.IGNORECASE)
    if m:
        text = m.group(1).strip()
    else:
        # first paragraph
        for para in re.split(r"\n\s*\n", body):
            p = para.strip()
            if p and not p.startswith("#"):
                text = p
                break
        else:
            text = ""
    return text[:max_chars]


FIT_LEVELS = {"high", "medium", "low", "incompatible"}
LEGACY_FIT_LABELS = {
    "easy": "high",
    "moderate": "medium",
    "hard": "low",
    "impossible": "incompatible",
}


def normalize_fit_level(value) -> str | None:
    """Normalize canonical or legacy fit values.

    Thresholds mirror config/policies/fit-levels.yaml. This copy is bundled
    because the bridge is installed outside the repository.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value >= 70:
            return "high"
        if value >= 50:
            return "medium"
        return "low"
    label = str(value).strip().lower()
    if label in FIT_LEVELS:
        return label
    return LEGACY_FIT_LABELS.get(label)


def fit_level_from_record(record: dict) -> str | None:
    for key in ("fit_level", "account_fit", "account_fit_score", "fit_score"):
        level = normalize_fit_level(record.get(key))
        if level:
            return level
    return None


# Native run receipts
_LAST_INPUT = {}

def _write_receipt(status: str, result_count: int = 0, error_code: str = "") -> None:
    run_id = _request_run_id(_LAST_INPUT)
    if not run_id:
        return
    runtime = _native_runtime()
    # Recheck under the same native lock used for run control. No state is
    # created, adopted, advanced or marked completed by a bridge operation.
    with runtime._locked(run_id):
        runtime._read(run_id)
        receipt = {
            "schema_version": 1,
            "bridge": "kb-bridge",
            "op": os.environ.get("KB_BRIDGE_OP", ""),
            "run_id": run_id,
            "called_at": datetime.now().astimezone().isoformat(),
            "status": status,
            "result_count": max(0, int(result_count)),
        }
        if error_code:
            receipt["error_code"] = error_code
        target = runtime._run_dir(run_id) / "bridge-receipts.jsonl"
        runtime._check_components(target)
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("Receipt target must be an unshared regular file")
            with os.fdopen(fd, "a", encoding="utf-8") as handle:
                fd = -1
                handle.write(json.dumps(receipt, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if fd >= 0:
                os.close(fd)
