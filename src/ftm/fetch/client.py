from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

import requests

USER_AGENT = "follow-the-money/0.1 (+https://github.com/)"

Status = Literal["new", "unchanged", "updated"]


@dataclass(frozen=True)
class FetchResult:
    status: Status
    body: bytes | None
    sha256: str | None
    etag: str | None
    last_modified: str | None


def get_with_cache(
    url: str,
    *,
    prev_etag: str | None = None,
    prev_lm: str | None = None,
    prev_sha: str | None = None,
    timeout: float = 30.0,
    session: requests.Session | None = None,
) -> FetchResult:
    headers = {"User-Agent": USER_AGENT}
    if prev_etag:
        headers["If-None-Match"] = prev_etag
    if prev_lm:
        headers["If-Modified-Since"] = prev_lm

    sess = session or requests
    resp = sess.get(url, headers=headers, timeout=timeout, allow_redirects=True)

    if resp.status_code == 304:
        return FetchResult(
            status="unchanged",
            body=None,
            sha256=prev_sha,
            etag=prev_etag,
            last_modified=prev_lm,
        )

    resp.raise_for_status()
    body = resp.content
    sha = hashlib.sha256(body).hexdigest()
    etag = resp.headers.get("ETag")
    last_modified = resp.headers.get("Last-Modified")

    if prev_sha is not None and sha == prev_sha:
        return FetchResult(
            status="unchanged",
            body=body,
            sha256=sha,
            etag=etag or prev_etag,
            last_modified=last_modified or prev_lm,
        )

    status: Status = "updated" if prev_sha is not None else "new"
    return FetchResult(
        status=status,
        body=body,
        sha256=sha,
        etag=etag,
        last_modified=last_modified,
    )
