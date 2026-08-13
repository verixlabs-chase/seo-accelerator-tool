from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


MAX_PUBLIC_PAGE_BYTES = 2_000_000


class _PublicPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.description = ""
        self.links: list[dict[str, str]] = []
        self.element_ids: set[str] = set()
        self.schema_blocks: list[dict[str, Any]] = []
        self._in_title = False
        self._current_link: dict[str, str] | None = None
        self._in_schema = False
        self._schema_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {str(key).lower(): str(value or "") for key, value in attrs}
        element_id = attributes.get("id", "").strip()
        if element_id:
            self.element_ids.add(element_id)
        lowered = tag.lower()
        if lowered == "title":
            self._in_title = True
        elif lowered == "meta" and attributes.get("name", "").lower() == "description":
            self.description = attributes.get("content", "").strip()
        elif lowered == "a":
            self._current_link = {"href": attributes.get("href", "").strip(), "text": ""}
        elif lowered == "script" and "ld+json" in attributes.get("type", "").lower():
            self._in_schema = True
            self._schema_parts = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self._in_title = False
        elif lowered == "a" and self._current_link is not None:
            self._current_link["text"] = _compact(self._current_link["text"])
            self.links.append(self._current_link)
            self._current_link = None
        elif lowered == "script" and self._in_schema:
            self._in_schema = False
            try:
                parsed = json.loads("".join(self._schema_parts))
            except (json.JSONDecodeError, TypeError):
                return
            if isinstance(parsed, dict):
                self.schema_blocks.append(parsed)
            elif isinstance(parsed, list):
                self.schema_blocks.extend(item for item in parsed if isinstance(item, dict))

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._current_link is not None:
            self._current_link["text"] += data
        if self._in_schema:
            self._schema_parts.append(data)

    @property
    def title(self) -> str:
        return _compact("".join(self.title_parts))


def verify_public_mutation_delivery(
    *,
    base_url: str,
    mutations: list[dict[str, Any]],
    results: list[dict[str, Any]],
    timeout_seconds: int,
) -> dict[str, Any]:
    by_id = {
        str(item.get("mutation_id") or ""): item for item in results if isinstance(item, dict)
    }
    verifications: list[dict[str, Any]] = []
    page_cache: dict[str, tuple[_PublicPageParser | None, str | None]] = {}

    for mutation in mutations:
        mutation_id = str(mutation.get("mutation_id") or "")
        result = by_id.get(mutation_id, {})
        action = str(mutation.get("action") or "")
        try:
            verification_url = _verification_url(base_url, mutation, result)
        except RuntimeError as exc:
            verifications.append(
                _verification_result(
                    mutation_id=mutation_id,
                    action=action,
                    target_url="",
                    status="failed",
                    passed=False,
                    message=str(exc),
                )
            )
            continue
        if action == "publish_content_page" and _is_non_public_draft(mutation):
            after_state = result.get("after_state") if isinstance(result.get("after_state"), dict) else {}
            created = bool(after_state.get("post_id"))
            verifications.append(
                _verification_result(
                    mutation_id=mutation_id,
                    action=action,
                    target_url=verification_url,
                    status="not_public" if created else "failed",
                    passed=created,
                    message=(
                        "WordPress saved the page as a draft, so there is no public page to check yet."
                        if created
                        else "WordPress did not return proof that the draft was created."
                    ),
                )
            )
            continue

        if verification_url not in page_cache:
            try:
                html = _fetch_public_html(verification_url, timeout_seconds=timeout_seconds)
                parser = _PublicPageParser()
                parser.feed(html)
                page_cache[verification_url] = (parser, None)
            except RuntimeError as exc:
                page_cache[verification_url] = (None, str(exc))
        page, fetch_error = page_cache[verification_url]
        if page is None:
            verifications.append(
                _verification_result(
                    mutation_id=mutation_id,
                    action=action,
                    target_url=verification_url,
                    status="failed",
                    passed=False,
                    message=fetch_error or "The public page could not be checked.",
                )
            )
            continue
        passed, message = _check_mutation(page, mutation, verification_url)
        verifications.append(
            _verification_result(
                mutation_id=mutation_id,
                action=action,
                target_url=verification_url,
                status="verified" if passed else "failed",
                passed=passed,
                message=message,
            )
        )

    failures = [item for item in verifications if not item["passed"]]
    return {
        "passed": not failures and bool(verifications),
        "verified_at": datetime.now(UTC).isoformat(),
        "pages_checked": len(page_cache),
        "checks_total": len(verifications),
        "checks_passed": len(verifications) - len(failures),
        "checks_failed": len(failures),
        "rollback_available": all(
            bool((by_id.get(str(item.get("mutation_id") or ""), {}).get("rollback_payload")))
            for item in mutations
        ),
        "results": verifications,
    }


def _fetch_public_html(url: str, *, timeout_seconds: int) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["insightos_verify"] = uuid.uuid4().hex
    uncached_url = urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )
    req = request.Request(
        uncached_url,
        method="GET",
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Cache-Control": "no-cache",
            "User-Agent": "InsightOS-Public-Verification/1.0",
        },
    )
    try:
        with request.urlopen(req, timeout=float(timeout_seconds)) as response:
            if _normalized_host(str(response.geturl() or "")) != _normalized_host(url):
                raise RuntimeError("The public page redirected to a different website.")
            content_type = str(response.headers.get("Content-Type") or "").lower()
            if "html" not in content_type:
                raise RuntimeError("The public URL did not return a website page.")
            raw = response.read(MAX_PUBLIC_PAGE_BYTES + 1)
    except HTTPError as exc:
        raise RuntimeError(f"The public page returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("The public page could not be reached after the change.") from exc
    if len(raw) > MAX_PUBLIC_PAGE_BYTES:
        raise RuntimeError("The public page was too large to verify safely.")
    return raw.decode("utf-8", errors="replace")


def _check_mutation(
    page: _PublicPageParser,
    mutation: dict[str, Any],
    page_url: str,
) -> tuple[bool, str]:
    action = str(mutation.get("action") or "")
    payload = mutation.get("payload") if isinstance(mutation.get("payload"), dict) else {}
    if action == "update_meta_title":
        expected = _compact(str(payload.get("title") or payload.get("value") or ""))
        passed = bool(expected) and page.title == expected
        return passed, "The public page title matches the approved value." if passed else "The public page title does not match the approved value yet."
    if action == "update_meta_description":
        expected = _compact(str(payload.get("description") or payload.get("value") or ""))
        passed = bool(expected) and _compact(page.description) == expected
        return passed, "The public search description matches the approved value." if passed else "The public search description does not match the approved value yet."
    if action == "insert_internal_link":
        expected_href = urljoin(page_url, str(payload.get("target_url") or ""))
        expected_text = _compact(str(payload.get("anchor_text") or ""))
        passed = any(
            urljoin(page_url, link["href"]) == expected_href
            and _compact(link["text"]).casefold() == expected_text.casefold()
            for link in page.links
        )
        return passed, "The approved internal link is visible on the public page." if passed else "The approved internal link is not visible on the public page yet."
    if action == "create_internal_anchor":
        expected_id = _slugify(str(payload.get("anchor_id") or payload.get("anchor_text") or ""))
        passed = bool(expected_id) and expected_id in page.element_ids
        return passed, "The approved page anchor is visible on the public page." if passed else "The approved page anchor is not visible on the public page yet."
    if action == "add_schema_markup":
        schema = payload.get("schema") or payload.get("schema_json") or payload.get("value")
        expected_type = str(payload.get("schema_type") or "")
        if isinstance(schema, dict):
            expected_type = str(schema.get("@type") or expected_type)
        found_types = set()
        for block in page.schema_blocks:
            _collect_schema_types(block, found_types)
        passed = bool(expected_type) and expected_type in found_types
        return passed, "The approved structured details are visible on the public page." if passed else "The approved structured details are not visible on the public page yet."
    if action == "publish_content_page":
        expected_title = _compact(str(payload.get("title") or ""))
        passed = bool(expected_title) and page.title == expected_title
        return passed, "The approved page is publicly available." if passed else "The new page is not publicly visible with the approved title yet."
    return False, "InsightOS does not have a public verification rule for this change type."


def _verification_url(
    base_url: str,
    mutation: dict[str, Any],
    result: dict[str, Any],
) -> str:
    after_state = result.get("after_state") if isinstance(result.get("after_state"), dict) else {}
    candidate = str(
        after_state.get("target_url")
        or mutation.get("source_url")
        or mutation.get("target_url")
        or "/"
    )
    resolved = urljoin(base_url.rstrip("/") + "/", candidate)
    if _normalized_host(resolved) != _normalized_host(base_url):
        raise RuntimeError("The public verification URL does not belong to the connected website.")
    return resolved


def _verification_result(
    *,
    mutation_id: str,
    action: str,
    target_url: str,
    status: str,
    passed: bool,
    message: str,
) -> dict[str, Any]:
    return {
        "mutation_id": mutation_id,
        "mutation_type": action,
        "target_url": target_url,
        "status": status,
        "passed": passed,
        "message": message,
    }


def _is_non_public_draft(mutation: dict[str, Any]) -> bool:
    payload = mutation.get("payload") if isinstance(mutation.get("payload"), dict) else {}
    status = str(payload.get("status") or payload.get("publication_state") or "draft").lower()
    return status != "publish"


def _collect_schema_types(value: Any, output: set[str]) -> None:
    if isinstance(value, dict):
        raw_type = value.get("@type")
        if isinstance(raw_type, str):
            output.add(raw_type)
        elif isinstance(raw_type, list):
            output.update(str(item) for item in raw_type if item)
        for child in value.values():
            _collect_schema_types(child, output)
    elif isinstance(value, list):
        for child in value:
            _collect_schema_types(child, output)


def _normalized_host(value: str) -> str:
    parsed = urlsplit(value if "://" in value else f"https://{value}")
    host = str(parsed.hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
