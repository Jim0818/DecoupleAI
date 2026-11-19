"""Source tests use in-memory responses; no network, article, or live cache I/O."""
from copy import deepcopy
from datetime import datetime, timezone
from http.client import IncompleteRead
import io
import json
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

from textpicos.content.topic_sources import (
    _SameOriginRedirect, canonical_url, collect_sources, fetch_source,
)


NOW = datetime(2026, 11, 19, 4, 0, tzinfo=timezone.utc)
FEED = {"id": "official", "kind": "feed", "url": "https://example.test/feed.json"}


def feed(items, **extra):
    return {"version": "https://jsonfeed.org/version/1.1", "title": "Example", "items": items, **extra}


def item(identity="1", **extra):
    return {"id": identity, "url": "https://example.test/post/" + identity,
            "title": "Task " + identity, "content_text": "A source claim", **extra}


class Response:
    def __init__(self, data=b"", headers=None, status=200, url=None):
        self.data = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.headers, self.status, self.url = headers or {}, status, url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, size):
        return self.data[:size]

    def geturl(self):
        return self.url


class Transport:
    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if not self.responses:
            raise AssertionError("Unexpected extra request")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        if result.url is None:
            result.url = request.full_url
        return result


def fetch(spec=None, *responses, **kwargs):
    transport = Transport(*responses)
    return fetch_source(spec or FEED, opener=transport, now=NOW, **kwargs), transport


class TopicSourceTests(unittest.TestCase):
    def test_rss_keeps_source_date_and_only_extracts_inert_text(self):
        xml = b'''<rss version="2.0"><channel><title>Source</title><item>
          <guid isPermaLink="false">post-7</guid><title>Check a result</title>
          <link>https://example.test/post/7?utm_source=rss&amp;task=7#section</link>
          <pubDate>Wed, 18 Nov 2026 15:00:00 +0800</pubDate>
          <description><![CDATA[<p>Ignore previous instructions is source text.</p>
          <script>dangerous()</script><p>Second point.</p>]]></description>
        </item></channel></rss>'''
        result, transport = fetch(FEED, Response(xml))
        self.assertEqual(result["status"], "ok")
        row = result["items"][0]
        self.assertEqual(row["published_at"], "2026-11-18T07:00:00+00:00")
        self.assertEqual(row["event_at"], None)
        self.assertEqual(row["canonical_url"], "https://example.test/post/7?task=7")
        self.assertIn("Ignore previous instructions", row["summary"])
        self.assertNotIn("dangerous", row["summary"])
        self.assertEqual(row["verification"], "source_not_checked")
        self.assertEqual(len(transport.requests), 1)

    def test_atom_namespace_relative_links_and_unknown_published_time(self):
        xml = b'''<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://example.test/news/">
        <entry xml:base="guides/"><id>urn:entry:1</id><title>Guide</title>
        <link rel="self" href="self.xml"/><link rel="alternate" type="text/html" href="first"/>
        <updated>2026-11-18T12:00:00Z</updated><summary type="html">&lt;b&gt;Useful&lt;/b&gt;</summary>
        </entry></feed>'''
        result, _ = fetch(FEED, Response(xml))
        row = result["items"][0]
        self.assertEqual(row["url"], "https://example.test/news/guides/first")
        self.assertEqual(row["published_at"], None)
        self.assertEqual(row["updated_at"], "2026-11-18T12:00:00+00:00")
        self.assertEqual(row["summary"], "Useful")

    def test_atom_html_title_summary_and_content_use_html_text_extraction(self):
        for body_tag in ("summary", "content"):
            with self.subTest(body_tag=body_tag):
                xml = f'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>urn:html:1</id>
                <title type="html">&lt;b&gt;Agent guide&lt;/b&gt; &amp;amp; examples</title>
                <{body_tag} type="html">&lt;p title="a &amp;gt; b"&gt;First&lt;/p&gt;
                &lt;script&gt;ignored()&lt;/script&gt;&lt;p&gt;Second &amp;amp; last&lt;/p&gt;</{body_tag}>
                </entry></feed>'''.encode()
                result, _ = fetch(FEED, Response(xml))
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["items"][0]["title"], "Agent guide & examples")
                self.assertEqual(result["items"][0]["summary"], "First Second & last")

    def test_atom_xhtml_title_summary_and_content_include_descendant_text(self):
        for body_tag in ("summary", "content"):
            with self.subTest(body_tag=body_tag):
                xml = f'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>urn:xhtml:1</id>
                <title type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml"><b>Agent</b>
                guide &amp; examples</div></title>
                <{body_tag} type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">
                First <b>nested</b> paragraph.\nSecond &amp; last.</div></{body_tag}>
                </entry></feed>'''.encode()
                result, _ = fetch(FEED, Response(xml))
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["items"][0]["title"], "Agent guide & examples")
                self.assertEqual(result["items"][0]["summary"], "First nested paragraph. Second & last.")

    def test_atom_plain_text_keeps_literal_markup_and_entity_spellings(self):
        for body_tag in ("summary", "content"):
            with self.subTest(body_tag=body_tag):
                xml = f'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>urn:text:1</id>
                <title type="text">Literal &lt;b&gt;bold&lt;/b&gt; &amp;lt;tag&amp;gt;</title>
                <{body_tag}>Keep &lt;i&gt;literal&lt;/i&gt; and &amp;amp; spelling.</{body_tag}>
                </entry></feed>'''.encode()
                result, _ = fetch(FEED, Response(xml))
                self.assertEqual(result["items"][0]["title"], "Literal <b>bold</b> &lt;tag&gt;")
                self.assertEqual(result["items"][0]["summary"], "Keep <i>literal</i> and &amp; spelling.")

    def test_json_feed_missing_title_body_and_date_are_not_invented(self):
        result, _ = fetch(FEED, Response(feed([{"id": 7, "url": "https://example.test/post/7",
                                                   "external_url": "https://origin.test/announcement"}])))
        row = result["items"][0]
        self.assertEqual(row["native_id"], "7")
        self.assertEqual(row["title"], "")
        self.assertEqual(row["summary"], "")
        self.assertFalse(row["content_available"])
        self.assertIsNone(row["published_at"])
        self.assertEqual(row["url"], "https://example.test/post/7")
        self.assertEqual(row["external_url"], "https://origin.test/announcement")

    def test_partial_invalid_feed_items_have_explicit_warning(self):
        result, _ = fetch(FEED, Response(feed([None, item()])))
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["warnings"], ["omitted_invalid_items:1"])
        invalid, _ = fetch(FEED, Response(feed([{"title": "Missing identity"}])))
        self.assertEqual(invalid["status"], "invalid_response")

    def test_empty_and_invalid_feed_are_distinct(self):
        empty, _ = fetch(FEED, Response(feed([])))
        bad, _ = fetch(FEED, Response(b"<html>Not a feed</html>"))
        self.assertEqual(empty["status"], "empty")
        self.assertEqual(bad["status"], "invalid_response")

    def test_entity_declaration_is_rejected(self):
        result, _ = fetch(FEED, Response(b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///private">]><rss/>'))
        self.assertEqual(result["status"], "invalid_response")

    def test_release_publication_time_draft_filter_and_metadata(self):
        spec = {"id": "releases", "kind": "github_releases", "repo": "owner/repo"}
        row = {"id": 15, "name": "Version 1", "tag_name": "v1", "html_url": "https://github.com/owner/repo/releases/tag/v1",
               "created_at": "2020-01-01T00:00:00Z", "published_at": "2026-11-18T00:00:00Z",
               "body": None, "prerelease": True, "final_score": 99}
        result, _ = fetch(spec, Response([row, {**row, "id": 16, "draft": True}]))
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["published_at"], "2026-11-18T00:00:00+00:00")
        self.assertTrue(result["items"][0]["metadata"]["prerelease"])
        self.assertNotIn("final_score", json.dumps(result))

    def test_issues_exclude_pull_requests_and_send_since_as_update_filter(self):
        spec = {"id": "issues", "kind": "github_issues", "repo": "owner/repo",
                "since": "2026-11-01T00:00:00Z", "state": "all"}
        row = {"id": 4, "number": 3, "title": "Task failed", "body": "Steps", "html_url": "https://github.com/owner/repo/issues/3",
               "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-11-18T00:00:00Z"}
        result, transport = fetch(spec, Response([{**row, "id": 5, "pull_request": {}}, row]))
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["published_at"], "2026-10-01T00:00:00+00:00")
        query = parse_qs(urlsplit(transport.requests[0][0].full_url).query)
        self.assertEqual(query["since"], ["2026-11-01T00:00:00+00:00"])
        self.assertEqual(query["state"], ["all"])

    def test_graphql_missing_auth_does_not_request(self):
        spec = {"id": "discussions", "kind": "github_discussions", "repo": "owner/repo", "token_env": "TEST_TOPIC_TOKEN"}
        result, transport = fetch(spec, environ={})
        self.assertEqual(result["status"], "auth_required")
        self.assertFalse(transport.requests)

    def test_graphql_uses_fixed_read_query_and_never_returns_token(self):
        spec = {"id": "discussions", "kind": "github_discussions", "repo": "owner/repo", "token_env": "TEST_TOPIC_TOKEN"}
        payload = {"data": {"repository": {"discussions": {"nodes": [{"id": "D_1", "number": 1, "title": "How?",
                   "bodyText": "Question", "url": "https://github.com/owner/repo/discussions/1", "updatedAt": "2026-11-18T00:00:00Z"}],
                   "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"}}}}}
        result, transport = fetch(spec, Response(payload), environ={"TEST_TOPIC_TOKEN": "private-token-value"})
        request = transport.requests[0][0]
        body = json.loads(request.data)
        self.assertTrue(body["query"].startswith("query("))
        self.assertNotIn("mutation", body["query"])
        self.assertEqual(body["variables"]["repo"], "repo")
        self.assertEqual(result["next_cursor"], {"after": "cursor-1", "offset": 0})
        self.assertNotIn("private-token-value", json.dumps(result))
        self.assertIsNone(result["items"][0]["published_at"])

    def test_graphql_http_200_errors_are_not_empty_success(self):
        spec = {"id": "discussions", "kind": "github_discussions", "repo": "owner/repo", "token_env": "TOKEN"}
        result, _ = fetch(spec, Response({"data": {"repository": None}, "errors": [{"message": "No permission"}]}), environ={"TOKEN": "secret"})
        self.assertEqual(result["status"], "invalid_response")

    def test_conditional_get_304_preserves_source_date_and_reports_no_new_items(self):
        first, _ = fetch(FEED, Response(feed([item(date_published="2020-01-01T00:00:00Z")]),
                                       headers={"ETag": '"one"', "Last-Modified": "Wed, 18 Nov 2026 00:00:00 GMT"}))
        old = deepcopy(first["state"])
        response = HTTPError(FEED["url"], 304, "Not Modified", {}, io.BytesIO())
        later = datetime(2026, 11, 20, tzinfo=timezone.utc)
        transport = Transport(response)
        result = fetch_source(FEED, state=old, opener=transport, now=later)
        self.assertEqual(result["status"], "not_modified")
        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["items"][0]["published_at"], "2020-01-01T00:00:00+00:00")
        self.assertTrue(result["items"][0]["from_cache"])
        headers = {k.lower(): v for k, v in transport.requests[0][0].header_items()}
        self.assertEqual(headers["if-none-match"], '"one"')
        self.assertIn("if-modified-since", headers)
        self.assertEqual(old, first["state"])

    def test_changed_item_is_updated_and_duplicate_id_is_returned_once(self):
        first, _ = fetch(FEED, Response(feed([item()])))
        updated, _ = fetch(FEED, Response(feed([item(content_text="Changed"), item(content_text="Changed")]),
                                        headers={"ETag": '"two"'}), state=first["state"])
        self.assertEqual(len(updated["items"]), 1)
        self.assertEqual(updated["updated_count"], 1)
        self.assertEqual(updated["items"][0]["id"], first["items"][0]["id"])

    def test_not_modified_without_cache_is_invalid(self):
        result, _ = fetch(FEED, Response(status=304))
        self.assertEqual(result["status"], "invalid_response")

    def test_failure_does_not_replace_good_cache(self):
        first, _ = fetch(FEED, Response(feed([item()])))
        state = deepcopy(first["state"])
        failed, _ = fetch(FEED, URLError("network failure"), state=state)
        self.assertEqual(failed["status"], "unavailable")
        self.assertEqual(failed["items"], [])
        self.assertEqual(failed["state"], state)

    def test_corrupt_cache_and_cursor_fail_explicitly_without_escaping_source(self):
        first, _ = fetch(FEED, Response(feed([item()]), headers={"ETag": '"one"'}))
        broken = {"fingerprint": first["state"]["fingerprint"]}
        result, transport = fetch(FEED, state=broken)
        self.assertEqual(result["status"], "invalid_config")
        self.assertFalse(transport.requests)
        poisoned = deepcopy(first["state"])
        next(iter(poisoned["pages"].values()))["next"] = {"url": "https://other.test/capture", "offset": 0}
        result, transport = fetch({**FEED, "max_pages": 2}, Response(status=304), state=poisoned)
        self.assertEqual(result["status"], "invalid_response")
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(result["state"], poisoned)
        result, transport = fetch(FEED, cursor={"offset": 0})
        self.assertEqual(result["status"], "invalid_config")
        self.assertFalse(transport.requests)

    def test_relative_links_use_same_origin_redirect_destination(self):
        xml = b'''<rss version="2.0"><channel><item><guid isPermaLink="false">1</guid>
        <title>One</title><link>posts/one</link></item></channel></rss>'''
        result, _ = fetch(FEED, Response(xml, url="https://example.test/updates/rss"))
        self.assertEqual(result["items"][0]["url"], "https://example.test/updates/posts/one")

    def test_http_rate_limit_and_failure_are_explicit_and_not_retried(self):
        for code, headers, expected in [(404, {}, "unavailable"), (429, {"Retry-After": "90"}, "rate_limited"),
                                         (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1234"}, "rate_limited"),
                                         (401, {}, "auth_required")]:
            with self.subTest(code=code):
                result, transport = fetch(FEED, HTTPError(FEED["url"], code, "failure", headers, io.BytesIO()))
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["http_status"], code)
                self.assertEqual(len(transport.requests), 1)

    def test_response_size_and_timeout_are_bounded(self):
        result, transport = fetch({**FEED, "max_response_bytes": 10, "timeout_seconds": 2}, Response(b"{" + b"x" * 20))
        self.assertEqual(result["status"], "invalid_response")
        self.assertEqual(result["error"], "response_too_large")
        self.assertEqual(transport.requests[0][1], 2)
        failed, _ = fetch(FEED, TimeoutError())
        self.assertEqual(failed["status"], "unavailable")

    def test_invalid_config_never_requests(self):
        for patch in ({"take": True}, {"max_pages": 6}, {"url": "file:///private"}, {"id": 23},
                      {"url": "https://user:secret@example.test/feed"}, {"max_response_bytes": 0},
                      {"kind": "unknown"}, {"signal": []}):
            with self.subTest(patch=patch):
                result, transport = fetch({**FEED, **patch})
                self.assertEqual(result["status"], "invalid_config")
                self.assertFalse(transport.requests)

    def test_http_feed_requires_explicit_configuration(self):
        spec = {**FEED, "url": "http://localhost:1200/feed"}
        invalid, _ = fetch(spec)
        self.assertEqual(invalid["status"], "invalid_config")
        allowed, _ = fetch({**spec, "allow_http": True}, Response(feed([])))
        self.assertEqual(allowed["status"], "empty")

    def test_cross_origin_redirect_does_not_forward_authorization(self):
        request = Request("https://api.github.com/repos/owner/repo/issues", headers={"Authorization": "Bearer secret"})
        with self.assertRaises(HTTPError):
            _SameOriginRedirect().redirect_request(request, io.BytesIO(), 302, "Moved", {}, "https://other.test/capture")

    def test_authenticated_rest_does_not_reuse_token_scoped_etags(self):
        spec = {"id": "release", "kind": "github_releases", "repo": "owner/repo", "token_env": "TOKEN"}
        first, _ = fetch(spec, Response([], headers={"ETag": '"private"'}), environ={"TOKEN": "first-secret"})
        result, transport = fetch(spec, Response([]), state=first["state"], environ={"TOKEN": "second-secret"})
        self.assertFalse(any(k.lower() == "if-none-match" for k, _ in transport.requests[0][0].header_items()))
        self.assertNotIn("secret", json.dumps(result))

    def test_page_and_take_budgets_produce_resumable_offset(self):
        spec = {**FEED, "take": 3, "max_pages": 2}
        page2 = "https://example.test/feed.json?page=2"
        second = feed([item("3"), item("4")])
        result, transport = fetch(spec, Response(feed([item("1"), item("2")], next_url=page2)), Response(second))
        self.assertEqual([x["native_id"] for x in result["items"]], ["1", "2", "3"])
        self.assertEqual(len(transport.requests), 2)
        self.assertTrue(result["has_more"])
        self.assertEqual(result["next_cursor"]["offset"], 1)
        resumed, _ = fetch(spec, Response(second), state=result["state"], cursor=result["next_cursor"])
        self.assertEqual([x["native_id"] for x in resumed["items"]], ["4"])
        self.assertFalse(resumed["has_more"])

    def test_changed_page_rejects_offset_cursor_instead_of_skipping_items(self):
        spec = {**FEED, "take": 1}
        result, _ = fetch(spec, Response(feed([item("1"), item("2")])))
        resumed, _ = fetch(spec, Response(feed([item("new"), item("1"), item("2")])),
                           state=result["state"], cursor=result["next_cursor"])
        self.assertEqual(resumed["status"], "invalid_response")
        self.assertEqual(resumed["items"], [])
        self.assertEqual(resumed["state"], result["state"])

    def test_cross_origin_pagination_is_not_followed(self):
        result, transport = fetch({**FEED, "max_pages": 2}, Response(feed([item()], next_url="http://localhost/private")))
        self.assertEqual(result["status"], "invalid_response")
        self.assertEqual(len(transport.requests), 1)

    def test_repeated_page_is_detected_within_budget(self):
        result, transport = fetch({**FEED, "max_pages": 3}, Response(feed([item()], next_url=FEED["url"])))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["error"], "pagination_cycle")
        self.assertEqual(len(transport.requests), 1)

    def test_second_page_failure_returns_partial_without_replacing_state(self):
        result, _ = fetch({**FEED, "max_pages": 2}, Response(feed([item()], next_url=FEED["url"] + "?page=2")), URLError("failed"))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["state"], {})
        self.assertTrue(result["has_more"])

    def test_request_identity_change_does_not_send_old_conditional_headers(self):
        first, _ = fetch(FEED, Response(feed([item()]), headers={"ETag": '"one"'}))
        result, transport = fetch({**FEED, "url": "https://example.test/other"}, Response(feed([])), state=first["state"])
        headers = {k.lower(): v for k, v in transport.requests[0][0].header_items()}
        self.assertNotIn("if-none-match", headers)
        self.assertNotEqual(result["state"]["fingerprint"], first["state"]["fingerprint"])

    def test_collection_retains_provenance_for_same_url_and_source_failures(self):
        specs = [FEED, {**FEED, "id": "second"}, {**FEED, "id": "failed"}]
        transport = Transport(Response(feed([item(url="https://example.test/post?utm_source=one")])),
                              Response(feed([item("2", url="https://example.test/post?utm_source=two")])), URLError("offline"))
        result = collect_sources(specs, opener=transport, now=NOW)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(len(result["items"][0]["provenance"]), 2)
        self.assertEqual([x["status"] for x in result["sources"]], ["ok", "ok", "unavailable"])
        self.assertEqual(set(result["states"]), {"official", "second", "failed"})

    def test_collection_survives_mid_response_truncation_and_preserves_old_state(self):
        class TruncatedResponse(Response):
            def read(self, size):
                raise IncompleteRead(b'{"version":', 128)

        truncated_spec = {**FEED, "id": "truncated"}
        previous, _ = fetch(truncated_spec, Response(feed([item("2")])))
        old_state = deepcopy(previous["state"])
        transport = Transport(Response(feed([item("1")])), TruncatedResponse(), Response(feed([item("3")])))
        result = collect_sources([FEED, truncated_spec, {**FEED, "id": "after"}],
                                 states={"truncated": old_state}, opener=transport, now=NOW)
        self.assertEqual(result["status"], "partial")
        self.assertEqual([x["native_id"] for x in result["items"]], ["1", "3"])
        self.assertEqual([x["status"] for x in result["sources"]], ["ok", "unavailable", "ok"])
        self.assertEqual(result["sources"][1]["error"], "transport_error")
        self.assertEqual(result["states"]["truncated"], previous["state"])
        self.assertEqual(old_state, previous["state"])
        self.assertEqual(len(transport.requests), 3)

    def test_collection_validates_ids_and_retains_empty_success(self):
        no_sources = collect_sources([], now=NOW)
        self.assertEqual(no_sources["status"], "empty")
        duplicated = collect_sources([FEED, FEED], opener=Transport(), now=NOW)
        self.assertEqual(duplicated["status"], "invalid_config")
        result = collect_sources([FEED, {**FEED, "id": "failed"}], opener=Transport(Response(feed([])), URLError("offline")), now=NOW)
        self.assertEqual(result["status"], "partial")

    def test_canonicalization_preserves_meaningful_parameters(self):
        self.assertEqual(canonical_url("https://EXAMPLE.test:443/?q=Agent&q=Task&utm_source=x#part"),
                         "https://example.test/?q=Agent&q=Task")


if __name__ == "__main__":
    unittest.main()
