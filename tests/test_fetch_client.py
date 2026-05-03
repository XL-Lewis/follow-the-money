import hashlib

import responses

from ftm.fetch.client import get_with_cache


URL = "https://example.test/declaration.pdf"
BODY = b"%PDF-1.4 fake content for testing"
SHA = hashlib.sha256(BODY).hexdigest()


@responses.activate
def test_first_fetch_downloads_and_returns_bytes_etag_lm_sha():
    responses.add(
        responses.GET,
        URL,
        body=BODY,
        status=200,
        headers={
            "ETag": 'W/"abc"',
            "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT",
            "Content-Type": "application/pdf",
        },
    )

    result = get_with_cache(URL)

    assert result.status == "new"
    assert result.body == BODY
    assert result.sha256 == SHA
    assert result.etag == 'W/"abc"'
    assert result.last_modified == "Wed, 01 Jan 2025 00:00:00 GMT"


@responses.activate
def test_304_returns_unchanged_with_no_body():
    responses.add(responses.GET, URL, status=304)

    result = get_with_cache(URL, prev_etag='W/"abc"', prev_sha="x" * 64)

    assert result.status == "unchanged"
    assert result.body is None


@responses.activate
def test_200_with_same_sha_as_prev_returns_unchanged():
    responses.add(responses.GET, URL, body=BODY, status=200)

    result = get_with_cache(URL, prev_sha=SHA)

    assert result.status == "unchanged"
    assert result.sha256 == SHA


@responses.activate
def test_200_with_different_sha_returns_updated():
    responses.add(responses.GET, URL, body=BODY, status=200)

    result = get_with_cache(URL, prev_sha="0" * 64)

    assert result.status == "updated"
    assert result.body == BODY
    assert result.sha256 == SHA


@responses.activate
def test_sends_if_none_match_and_if_modified_since():
    captured = {}

    def callback(request):
        captured["headers"] = dict(request.headers)
        return (200, {}, BODY)

    responses.add_callback(responses.GET, URL, callback=callback)

    get_with_cache(
        URL,
        prev_etag='W/"abc"',
        prev_lm="Wed, 01 Jan 2025 00:00:00 GMT",
    )

    assert captured["headers"].get("If-None-Match") == 'W/"abc"'
    assert (
        captured["headers"].get("If-Modified-Since")
        == "Wed, 01 Jan 2025 00:00:00 GMT"
    )
