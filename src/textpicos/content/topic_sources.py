"""Bounded, read-only topic leads. Callers own configuration and cache storage.

``fetch_source`` returns a JSON-serializable ``state``; it never reads or writes
files. ``collect_sources`` accepts states/cursors keyed by the configured source
ID. A cursor is an opaque JSON object returned as ``next_cursor``. Starting a new
poll without a cursor always checks the first page, so new entries are not lost
while an older page is being consumed. No automatic schedule, retry, editorial
score, article fetch, or authorization to write content is implied.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
from html import unescape
from html.parser import HTMLParser
from http.client import HTTPException
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET


KINDS = {"feed", "github_releases", "github_issues", "github_discussions"}
SUCCESS = {"ok", "empty", "not_modified"}
ATOM = "{http://www.w3.org/2005/Atom}"
XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"
MAX_PAGE_ITEMS = 2000
MAX_STATE_PAGES = 5
MAX_SEEN_ITEMS = 2000
_DISCUSSIONS_QUERY = """query($owner:String!,$repo:String!,$first:Int!,$after:String) {
  repository(owner:$owner,name:$repo) {
    discussions(first:$first,after:$after,orderBy:{field:UPDATED_AT,direction:DESC}) {
      nodes { id number title url bodyText createdAt publishedAt updatedAt }
      pageInfo { endCursor hasNextPage }
    }
  }
}"""


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _positive(value, name, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer from 1 to {maximum}")
    return value


def _url(value, *, base=None, allow_http=False):
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        raise ValueError("Expected a nonempty HTTP(S) URL without whitespace")
    value = urljoin(base, value) if base else value
    p = urlsplit(value)
    p.port  # Validate malformed ports before making any request.
    if p.scheme not in ({"https", "http"} if allow_http else {"https"}) or not p.hostname:
        raise ValueError("Source URL must use HTTPS (HTTP requires explicit allow_http)")
    if p.username is not None or p.password is not None:
        raise ValueError("Credentials in URLs are not supported")
    return value


def _origin(url):
    p = urlsplit(url)
    return p.scheme.lower(), p.hostname.lower(), p.port or (443 if p.scheme == "https" else 80)


def canonical_url(url):
    """Remove only fragment/tracking fields; preserve meaningful query order."""
    if not url:
        return None
    _url(url, allow_http=True)
    p = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
    host = p.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    if p.port and p.port != (443 if p.scheme == "https" else 80):
        host += f":{p.port}"
    return urlunsplit((p.scheme.lower(), host, p.path or "/", urlencode(query), ""))


def _date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            stamp = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    return stamp.astimezone(timezone.utc).isoformat() if stamp.tzinfo is not None else None


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.ignore = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignore += 1
        elif not self.ignore:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.ignore:
            self.ignore -= 1

    def handle_data(self, data):
        if not self.ignore:
            self.parts.append(data)


def _text(value, html=False, limit=4000):
    if not isinstance(value, str):
        return ""
    if html:
        parser = _Text()
        parser.feed(value)
        value = "".join(parser.parts)
    return " ".join(unescape(value).split())[:limit]


def _atom_text(element, limit=4000):
    """Extract Atom text constructs without interpreting plain text as HTML."""
    if element is None:
        return ""
    kind = element.get("type", "text")
    if kind == "xhtml":
        value = "".join(element.itertext())
    elif kind == "html":
        parser = _Text()
        parser.feed(element.text or "")
        parser.close()
        value = "".join(parser.parts)
    else:
        # ElementTree has already decoded XML entities. Keep remaining literal
        # entity spellings and angle brackets in Atom's plain text constructs.
        value = element.text or ""
    return " ".join(value.split())[:limit]


def _link(value, base):
    if not value:
        return None
    try:
        return _url(value, base=base, allow_http=True)
    except (TypeError, ValueError):
        return None


def _item(spec, native_id, title, summary, url, *, published=None, updated=None,
          external_url=None, metadata=None, title_is_plain=False):
    if isinstance(native_id, bool) or not isinstance(native_id, (str, int)) or not str(native_id):
        raise ValueError("Item has no usable source identity")
    source_id = spec["id"]
    result = {"id": source_id + ":" + _digest(str(native_id))[:24],
              "native_id": str(native_id), "source_id": source_id, "kind": spec["kind"],
              "signal": spec.get("signal", "source_material"),
              "url": url, "canonical_url": canonical_url(url), "external_url": external_url,
              "title": title[:500] if title_is_plain else _text(title, limit=500), "summary": summary,
              "published_at": _date(published), "updated_at": _date(updated),
              "event_at": None, "content_available": bool(summary),
              "verification": "source_not_checked", "metadata": metadata or {}}
    if not (result["title"] or summary or url):
        raise ValueError("Item has no usable material")
    return result


def _feed_items(data, spec, base):
    warnings, rows = [], []
    title_is_plain = False
    if data.lstrip().startswith((b"{", b"[")):
        feed = json.loads(data.decode("utf-8-sig"))
        if (not isinstance(feed, dict) or feed.get("version") not in
                {"https://jsonfeed.org/version/1", "https://jsonfeed.org/version/1.1"}
                or not isinstance(feed.get("items"), list)):
            raise ValueError("Invalid JSON Feed")
        for row in feed["items"]:
            if not isinstance(row, dict):
                rows.append(None)
                continue
            summary = _text(row.get("summary") or row.get("content_text") or row.get("content_html"),
                            html=not (row.get("summary") or row.get("content_text")))
            rows.append((row.get("id"), row.get("title"), summary,
                         _link(row.get("url"), base), row.get("date_published"),
                         row.get("date_modified"), _link(row.get("external_url"), base)))
        next_page = feed.get("next_url")
    else:
        if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", data, re.I):
            raise ValueError("DTD and entities are not supported")
        root = ET.fromstring(data)
        if root.tag == ATOM + "feed":
            title_is_plain = True
            feed_base = urljoin(base, root.get(XML_BASE, ""))
            for entry in root.findall(ATOM + "entry"):
                entry_base = urljoin(feed_base, entry.get(XML_BASE, ""))
                links = [link for link in entry.findall(ATOM + "link")
                         if link.get("rel", "alternate") == "alternate"]
                chosen = next((x for x in links if x.get("type") == "text/html"), links[0] if links else None)
                url = (_link(chosen.get("href"), urljoin(entry_base, chosen.get(XML_BASE, "")))
                       if chosen is not None else None)
                body = entry.find(ATOM + "summary")
                if body is None:
                    body = entry.find(ATOM + "content")
                summary = _atom_text(body)
                rows.append((entry.findtext(ATOM + "id") or url,
                             _atom_text(entry.find(ATOM + "title"), limit=500), summary, url,
                             entry.findtext(ATOM + "published"), entry.findtext(ATOM + "updated"), None))
            next_link = next((x for x in root.findall(ATOM + "link") if x.get("rel") == "next"), None)
            next_page = urljoin(feed_base, next_link.get("href", "")) if next_link is not None else None
        elif root.tag == "rss" and root.find("channel") is not None:
            channel = root.find("channel")
            for row in channel.findall("item"):
                url = _link(row.findtext("link"), base)
                guid = row.findtext("guid")
                if not url and row.find("guid") is not None and row.find("guid").get("isPermaLink", "true") == "true":
                    url = _link(guid, base)
                title = row.findtext("title")
                summary = _text(row.findtext("description") or row.findtext("{http://purl.org/rss/1.0/modules/content/}encoded"), html=True)
                published = row.findtext("pubDate") or row.findtext("{http://purl.org/dc/elements/1.1/}date")
                native_id = guid or url or _digest([title, published, summary])
                rows.append((native_id, title, summary, url, published, None, None))
            next_link = next((x for x in channel.findall(ATOM + "link") if x.get("rel") == "next"), None)
            next_page = urljoin(base, next_link.get("href", "")) if next_link is not None else None
        else:
            raise ValueError("Expected RSS 2.0, Atom, or JSON Feed")
    if len(rows) > MAX_PAGE_ITEMS:
        raise ValueError("Feed exceeds the item parsing budget")
    items, invalid = [], 0
    for row in rows:
        try:
            if row is None:
                raise ValueError("Invalid item")
            native_id, title, summary, url, published, updated, external = row
            items.append(_item(spec, native_id, title, summary, url, published=published,
                               updated=updated, external_url=external, title_is_plain=title_is_plain))
        except (TypeError, ValueError):
            invalid += 1
    if invalid:
        warnings.append(f"omitted_invalid_items:{invalid}")
        if not items:
            raise ValueError("No usable feed items")
    return items, next_page, warnings


def _github_items(data, spec):
    payload = json.loads(data)
    kind, warnings, after = spec["kind"], [], None
    if kind == "github_discussions":
        if not isinstance(payload, dict):
            raise ValueError("GraphQL response must be an object")
        errors = payload.get("errors")
        if errors:
            warnings.append("graphql_partial_errors")
        repository = (payload.get("data") or {}).get("repository")
        if not isinstance(repository, dict) or not isinstance(repository.get("discussions"), dict):
            raise ValueError("GraphQL repository/discussions unavailable")
        connection = repository["discussions"]
        rows = connection.get("nodes")
        page_info = connection.get("pageInfo")
        if not isinstance(page_info, dict) or not isinstance(page_info.get("hasNextPage"), bool):
            raise ValueError("GraphQL pageInfo is invalid")
        if page_info["hasNextPage"]:
            after = page_info.get("endCursor")
            if not isinstance(after, str) or not after:
                raise ValueError("GraphQL continuation cursor is missing")
    else:
        rows = payload
    if not isinstance(rows, list) or len(rows) > MAX_PAGE_ITEMS:
        raise ValueError("Expected a bounded GitHub item array")
    items, invalid = [], 0
    for row in rows:
        try:
            if not isinstance(row, dict):
                raise ValueError("Invalid GitHub item")
            if kind == "github_issues" and "pull_request" in row:
                continue
            if kind == "github_releases" and row.get("draft"):
                continue
            if kind == "github_discussions":
                native_id, title = row.get("id"), row.get("title")
                url = _link(row.get("url"), "https://github.com/")
                summary = _text(row.get("bodyText"))
                published, updated = row.get("publishedAt"), row.get("updatedAt")
                metadata = {"number": row.get("number"), "created_at": _date(row.get("createdAt"))}
            else:
                native_id = row.get("id")
                url = _link(row.get("html_url"), "https://github.com/")
                title = row.get("name") or row.get("tag_name") if kind == "github_releases" else row.get("title")
                summary = _text(row.get("body"))
                published = row.get("published_at") if kind == "github_releases" else row.get("created_at")
                updated = row.get("updated_at")
                metadata = ({"tag": row.get("tag_name"), "prerelease": bool(row.get("prerelease"))}
                            if kind == "github_releases" else {"number": row.get("number"), "state": row.get("state"), "comments": row.get("comments")})
            items.append(_item(spec, native_id, title, summary, url, published=published,
                               updated=updated, metadata=metadata))
        except (TypeError, ValueError):
            invalid += 1
    if invalid:
        warnings.append(f"omitted_invalid_items:{invalid}")
        if not items:
            raise ValueError("No usable GitHub items")
    return items, after, warnings


class _SameOriginRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _url(newurl, allow_http=True)
        if _origin(newurl) != _origin(req.full_url):
            raise HTTPError(req.full_url, code, "Cross-origin redirect blocked", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _configuration(spec, environ):
    if (not isinstance(spec, dict) or not isinstance(spec.get("id"), str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,79}", spec["id"])):
        raise ValueError("Source id must be a short lowercase identifier")
    kind = spec.get("kind")
    if kind not in KINDS:
        raise ValueError("Unsupported source kind")
    take = _positive(spec.get("take", 20), "take", 100)
    pages = _positive(spec.get("max_pages", 1), "max_pages", 5)
    timeout = _positive(spec.get("timeout_seconds", 15), "timeout_seconds", 60)
    size = _positive(spec.get("max_response_bytes", 2_000_000), "max_response_bytes", 10_000_000)
    if not isinstance(spec.get("signal", "source_material"), str):
        raise ValueError("signal must be text")
    headers = {"User-Agent": "TextPicOS topic discovery", "Accept-Encoding": "identity"}
    token = None
    if kind == "feed":
        if not isinstance(spec.get("allow_http", False), bool):
            raise ValueError("allow_http must be boolean")
        url = _url(spec.get("url"), allow_http=spec.get("allow_http", False))
        headers["Accept"] = "application/feed+json, application/atom+xml, application/rss+xml, application/xml, application/json, text/xml"
    else:
        repo = spec.get("repo", "")
        if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("repo must be owner/name")
        version = spec.get("api_version", "2026-03-10")
        if not isinstance(version, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", version):
            raise ValueError("api_version must be a date")
        headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": version})
        token_env = spec.get("token_env")
        if token_env is not None:
            if not isinstance(token_env, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", token_env):
                raise ValueError("token_env must name an environment variable")
            token = environ.get(token_env)
            if token:
                if not isinstance(token, str) or any(c.isspace() for c in token):
                    raise ValueError("Configured token is invalid")
                headers["Authorization"] = "Bearer " + token
        if kind == "github_discussions":
            url = "https://api.github.com/graphql"
        else:
            query = {"per_page": take}
            if kind == "github_issues":
                issue_state = spec.get("state", "all")
                if issue_state not in {"all", "open", "closed"}:
                    raise ValueError("Issue state must be open, closed, or all")
                query["state"] = issue_state
                if spec.get("since") is not None:
                    since = _date(spec["since"])
                    if since is None:
                        raise ValueError("since requires a timestamp with timezone")
                    query["since"] = since
            endpoint = "releases" if kind == "github_releases" else "issues"
            url = "https://api.github.com/repos/" + repo + "/" + endpoint + "?" + urlencode(query)
    fingerprint = _digest({"id": spec["id"], "kind": kind, "url": url,
                           "repo": spec.get("repo"), "take": take,
                           "max_response_bytes": size,
                           "signal": spec.get("signal"), "token_env": spec.get("token_env"),
                           "authenticated": bool(token), "api_version": spec.get("api_version", "2026-03-10")})
    return url, headers, take, pages, timeout, size, fingerprint, bool(token)


def _continuation(value, base, kind):
    if value is None:
        return None
    if kind == "github_discussions":
        if not isinstance(value, str) or not value or len(value) > 2048:
            raise ValueError("Invalid GraphQL cursor")
        return {"after": value, "offset": 0}
    value = _url(value, base=base, allow_http=urlsplit(base).scheme == "http")
    if _origin(value) != _origin(base):
        raise ValueError("Cross-origin pagination blocked")
    return {"url": value, "offset": 0}


def _next_link(headers):
    for part in headers.get("link", "").split(","):
        match = re.match(r'\s*<([^>]+)>\s*;(.*)', part)
        if match and re.search(r'\brel\s*=\s*["\']?next(?:["\']|\s|;|$)', match[2]):
            return match[1]
    return None


def _resume(value, base, kind):
    if (not isinstance(value, dict) or isinstance(value.get("offset", 0), bool)
            or not isinstance(value.get("offset", 0), int)
            or not 0 <= value.get("offset", 0) <= MAX_PAGE_ITEMS):
        raise ValueError("Invalid continuation offset")
    marker = value.get("after") if kind == "github_discussions" else value.get("url")
    position = _continuation(marker, base, kind)
    if position is None:
        if kind != "github_discussions":
            raise ValueError("Continuation URL is missing")
        position = {"after": None, "offset": 0}
    position["offset"] = value.get("offset", 0)
    if position["offset"]:
        if not isinstance(value.get("page_digest"), str) or not re.fullmatch(r"[a-f0-9]{64}", value["page_digest"]):
            raise ValueError("An offset cursor requires its original page digest")
        position["page_digest"] = value["page_digest"]
    return position


def fetch_source(spec, *, state=None, cursor=None, now=None, opener=None, environ=None):
    """Fetch at most ``take`` leads / ``max_pages`` requests; no filesystem I/O.

    Spec: id, kind, url (feed) or repo (GitHub), optional signal/take/max_pages/
    timeout_seconds/max_response_bytes/api_version/token_env/since/state.
    Persist returned state with the caller's lock/CAS mechanism. On failures the
    last good state is returned unchanged. Tokens are never returned or cached.
    """
    outcome = {"source_id": spec.get("id") if isinstance(spec, dict) else None,
               "kind": spec.get("kind") if isinstance(spec, dict) else None,
               "items": [], "warnings": [], "has_more": False, "next_cursor": None,
               "http_status": None, "retry_after": None, "requests": 0,
               "state": deepcopy(state) if isinstance(state, dict) else {}}
    try:
        stamp = now or datetime.now(timezone.utc)
        if not isinstance(stamp, datetime) or stamp.tzinfo is None:
            raise ValueError("now must be a timezone-aware datetime")
        observed = stamp.astimezone(timezone.utc).isoformat()
        outcome["fetched_at"] = observed
        url, headers, take, budget, timeout, size, fingerprint, authenticated = _configuration(spec, os.environ if environ is None else environ)
        kind = spec["kind"]
        outcome["source_url"] = url
        previous = deepcopy(state) if isinstance(state, dict) and state.get("fingerprint") == fingerprint else {}
        if previous and (previous.get("schema_version") != 1
                         or not isinstance(previous.get("pages"), dict)
                         or not isinstance(previous.get("seen"), dict)):
            raise ValueError("Invalid cache state")
        current = deepcopy(previous) or {"schema_version": 1, "fingerprint": fingerprint, "pages": {}, "seen": {}}
        position = {"after": None, "offset": 0} if kind == "github_discussions" else {"url": url, "offset": 0}
        if cursor is not None:
            position = _resume(cursor, url, kind)
        if kind == "github_discussions" and not authenticated:
            return {**outcome, "status": "auth_required", "error": "configured_token_missing"}
    except (TypeError, ValueError, KeyError, OverflowError):
        return {**outcome, "status": "invalid_config", "error": "invalid_source_configuration"}

    transport = opener or build_opener(_SameOriginRedirect()).open
    visited, all_items, returned_ids, cached_count, failure = set(), [], set(), 0, None
    while position is not None and outcome["requests"] < budget and len(all_items) < take:
        request_url, body = position.get("url", url), None
        if kind == "github_discussions":
            owner, repo = spec["repo"].split("/", 1)
            body = json.dumps({"query": _DISCUSSIONS_QUERY, "variables": {
                "owner": owner, "repo": repo, "first": take, "after": position["after"]}}).encode()
        key = _digest([request_url, body.decode() if body else None])
        if key in visited:
            failure = ("invalid_response", "pagination_cycle")
            break
        visited.add(key)
        cached = current["pages"].get(key)
        request_headers = dict(headers)
        # Do not reuse authenticated representations across changing token scopes.
        if not authenticated and isinstance(cached, dict):
            for old, new in (("etag", "If-None-Match"), ("last_modified", "If-Modified-Since")):
                if isinstance(cached.get(old), str):
                    request_headers[new] = cached[old]
        if body:
            request_headers["Content-Type"] = "application/json"
        request = Request(request_url, data=body, headers=request_headers)
        outcome["requests"] += 1
        try:
            try:
                with transport(request, timeout=timeout) as response:
                    status = getattr(response, "status", 200)
                    response_headers = {str(k).lower(): str(v) for k, v in response.headers.items()}
                    final_url = response.geturl() if hasattr(response, "geturl") else request_url
                    if _origin(final_url) != _origin(url):
                        raise ValueError("Cross-origin response blocked")
                    if status != 304:
                        data = response.read(size + 1)
            except HTTPError as exc:
                status = exc.code
                response_headers = {str(k).lower(): str(v) for k, v in (exc.headers or {}).items()}
                if status != 304:
                    outcome["http_status"] = status
                    outcome["retry_after"] = response_headers.get("retry-after") or response_headers.get("x-ratelimit-reset")
                    category = ("rate_limited" if status == 429 or (status == 403 and
                                (response_headers.get("x-ratelimit-remaining") == "0" or outcome["retry_after"]))
                                else "auth_required" if status == 401 else "unavailable")
                    failure = (category, f"http_{status}")
                    exc.close()
                    break
                exc.close()
            outcome["http_status"] = status
            if status == 304:
                if authenticated or not isinstance(cached, dict) or not isinstance(cached.get("items"), list):
                    raise ValueError("304 without usable cached response")
                page = deepcopy(cached)
                if page.get("next") is not None:
                    page["next"] = _resume(page["next"], url, kind)
                cached_count += 1
            else:
                if len(data) > size:
                    failure = ("invalid_response", "response_too_large")
                    break
                if status != 200 or response_headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
                    raise ValueError("Unsupported or oversized response")
                if kind == "feed":
                    items, next_value, warnings = _feed_items(data, spec, final_url)
                else:
                    items, next_value, warnings = _github_items(data, spec)
                    if kind != "github_discussions":
                        next_value = _next_link(response_headers)
                next_position = _continuation(next_value, final_url, kind)
                page = {"items": items, "next": next_position, "warnings": warnings,
                        "etag": response_headers.get("etag"),
                        "last_modified": response_headers.get("last-modified"), "retrieved_at": observed}
                current["pages"][key] = deepcopy(page)
            outcome["warnings"].extend(page.get("warnings", []))
            offset = position.get("offset", 0)
            page_digest = _digest(page["items"])
            if offset > len(page["items"]) or (offset and position.get("page_digest") != page_digest):
                raise ValueError("Page changed; continuation offset is no longer valid")
            for index in range(offset, len(page["items"])):
                row = deepcopy(page["items"][index])
                if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                    raise ValueError("Invalid cached item")
                if row["id"] not in returned_ids:
                    digest = _digest(row)
                    old = current["seen"].get(row["id"])
                    row["change"] = "new" if old is None else "unchanged" if old == digest else "updated"
                    row["observed_at"], row["retrieved_at"] = observed, page["retrieved_at"]
                    row["from_cache"] = status == 304
                    row["provenance"] = [{"source_id": spec["id"], "source_url": url,
                                          "native_id": row["native_id"], "url": row["url"],
                                          "external_url": row["external_url"], "observed_at": observed}]
                    all_items.append(row)
                    returned_ids.add(row["id"])
                    current["seen"].pop(row["id"], None)
                    current["seen"][row["id"]] = digest
                if len(all_items) == take:
                    position = ({**position, "offset": index + 1, "page_digest": page_digest}
                                if index + 1 < len(page["items"]) else page.get("next"))
                    break
            else:
                position = page.get("next")
        except (URLError, OSError, TimeoutError, HTTPException):
            failure = ("unavailable", "transport_error")
            break
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, ET.ParseError):
            failure = ("invalid_response", "invalid_source_payload")
            break

    if failure:
        outcome.update(status="partial" if all_items else failure[0], error=failure[1],
                       failure_status=failure[0], items=all_items, has_more=position is not None,
                       next_cursor=position)
        # Retry can safely replay; no failed or incomplete response replaces state.
        return outcome
    current["last_success_at"] = observed
    current["pages"] = dict(list(current["pages"].items())[-MAX_STATE_PAGES:])
    current["seen"] = dict(list(current["seen"].items())[-MAX_SEEN_ITEMS:])
    status = ("partial" if "graphql_partial_errors" in outcome["warnings"] else
              "not_modified" if cached_count == outcome["requests"] else "ok" if all_items else "empty")
    outcome.update(status=status, items=all_items, state=current,
                   has_more=position is not None, next_cursor=position,
                   new_count=sum(x["change"] == "new" for x in all_items),
                   updated_count=sum(x["change"] == "updated" for x in all_items))
    return outcome


def collect_sources(specs, *, states=None, cursors=None, now=None, opener=None, environ=None):
    """Collect explicitly selected sources serially and preserve every health result."""
    base = {"items": [], "sources": [], "states": {}}
    if not isinstance(specs, list) or len(specs) > 20 or not isinstance(states or {}, dict) or not isinstance(cursors or {}, dict):
        return {**base, "status": "invalid_config", "error": "invalid_source_selection"}
    ids = [s.get("id") if isinstance(s, dict) else None for s in specs]
    if any(not isinstance(s, str) for s in ids) or len(set(ids)) != len(ids):
        return {**base, "status": "invalid_config", "error": "duplicate_or_missing_source_id"}
    grouped = {}
    for spec in specs:
        key = spec["id"]
        result = fetch_source(spec, state=(states or {}).get(key), cursor=(cursors or {}).get(key),
                              now=now, opener=opener, environ=environ)
        base["states"][key] = result["state"]
        base["sources"].append({k: v for k, v in result.items() if k != "state"})
        for item in result["items"]:
            identity = item.get("canonical_url") or item["id"]
            if identity not in grouped:
                grouped[identity] = deepcopy(item)
            else:
                grouped[identity]["provenance"].extend(item["provenance"])
    base["items"] = list(grouped.values())
    statuses = [s["status"] for s in base["sources"]]
    if any(s not in SUCCESS for s in statuses):
        status = "partial" if base["items"] or any(s in SUCCESS for s in statuses) else "unavailable"
    else:
        status = "not_modified" if statuses and all(s == "not_modified" for s in statuses) else "ok" if base["items"] else "empty"
    return {**base, "status": status}
