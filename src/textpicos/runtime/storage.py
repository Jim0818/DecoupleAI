"""Small durable filesystem primitives; no project discovery or content scanning."""
from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
    finally:
        os.close(descriptor)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _article_content(data: bytes, path: Path) -> bytes | None:
    """Project known Markdown content; ambiguous metadata stays byte-sensitive.

    Tags and workflow_status are the only non-content fields omitted. Unknown
    fields, title, dates, evidence and author boundaries remain dependencies.
    Returning None means conservative full-file comparison, never an empty body.
    """
    if path.suffix.lower() not in {".md", ".markdown"}:
        return None
    try:
        import yaml

        class UniqueMappingLoader(yaml.SafeLoader):
            def construct_mapping(self, node, deep=False):
                seen = set()
                for key_node, _ in node.value:
                    key = self.construct_object(key_node, deep=deep)
                    if not isinstance(key, str) or key in seen:
                        raise yaml.YAMLError("Ambiguous frontmatter mapping")
                    seen.add(key)
                return super().construct_mapping(node, deep=deep)

        text = data.decode("utf-8")
        lines = text.splitlines(keepends=True)
        metadata, body = {}, text
        if lines and lines[0].rstrip("\r\n \t") == "---":
            end = next((i for i, line in enumerate(lines[1:], 1)
                        if line.rstrip("\r\n \t") == "---"), None)
            if end is None:
                return None
            metadata = yaml.load("".join(lines[1:end]), Loader=UniqueMappingLoader)
            if not isinstance(metadata, dict):
                return None
            body = "".join(lines[end + 1:])
        content = {key: value for key, value in metadata.items()
                   if key not in {"tags", "workflow_status"}}
        encoded = yaml.safe_dump(content, allow_unicode=True, sort_keys=True).encode("utf-8")
        return encoded + b"\0" + body.encode("utf-8")
    except (ImportError, UnicodeError, ValueError, TypeError, RecursionError):
        return None
    except yaml.YAMLError:
        return None


def file_version(path: Path, *, version_scope: str = "file") -> dict | None:
    """Hash one selected regular file, optionally projecting article content.

    Full-file versions remain the default and the only write-CAS versions.
    Content projections are explicit input dependencies, not editing decisions.
    """
    if version_scope not in ("file", "article_content"):
        raise ValueError(f"Unknown input version scope: {version_scope}")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"Expected a regular file: {path}")
        digest = hashlib.sha256()
        content_blocks = [] if version_scope == "article_content" else None
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            if content_blocks is not None:
                content_blocks.append(block)
        after = os.fstat(stream.fileno())
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"File changed while reading: {path}")
    result = {"sha256": digest.hexdigest(), "size": after.st_size}
    if content_blocks is not None:
        projected = _article_content(b"".join(content_blocks), path)
        if projected is not None:
            result = {"sha256": hashlib.sha256(projected).hexdigest(), "size": len(projected)}
        result.update(version_scope="article_content",
                      projection="frontmatter_body_v1" if projected is not None else "full_file")
    return result


def durable_copy(source: Path, target: Path) -> None:
    """Copy one file into a private transaction area, preserving exact bytes."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        for block in iter(lambda: incoming.read(1024 * 1024), b""):
            outgoing.write(block)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    fsync_directory(target.parent)


def replace_from_copy(source: Path, target: Path) -> None:
    """Atomic replacement of one target; the caller holds the transaction lock."""
    target.parent.mkdir(parents=True, exist_ok=True)
    previous_mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644
    descriptor, temporary = tempfile.mkstemp(prefix=".commit-", dir=target.parent)
    try:
        with source.open("rb") as incoming, os.fdopen(descriptor, "wb") as outgoing:
            for block in iter(lambda: incoming.read(1024 * 1024), b""):
                outgoing.write(block)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        os.chmod(temporary, previous_mode)
        os.replace(temporary, target)
        fsync_directory(target.parent)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)
